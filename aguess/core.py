"""Durable state machine. No AstrBot, network or LLM dependency."""
import json
import random
import re
import sqlite3
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

from .matcher import label, parse, assess, answer_key, solution_rules
from .version import PLUGIN_VERSION, MATCHER_VERSION, BANK_VERSION

HELP = ('a一把：普通模式；a一把 困难：猜算法组合。\n'
        'a猜 算法 + 算法｜a提示｜a进度｜a结束｜a再来\n'
        'a题意｜a题解｜a上局｜a申诉 说明｜a帮助\n'
        '管理员：a题库状态｜a申诉列表｜a处理申诉 编号 状态 理由\n'
        '全群共享十次有效答案；主动提示不扣次数；重复答案不扣次数。')
COMMANDS = ('一把', '猜', '提示', '进度', '结束', '再来', '题意', '题解', '申诉', '帮助', '题库状态', '上局', '申诉列表', '处理申诉')


class Settlement(str):
    """A string reply carrying its durable settlement ID until send completes."""
    def __new__(cls, text, game_id):
        obj = super().__new__(cls, text)
        obj.game_id = game_id
        return obj


def command(text, wake_prefixes=()):
    text = unicodedata.normalize('NFKC', text).strip()
    for prefix in sorted(wake_prefixes, key=len, reverse=True):
        if prefix and text.startswith(prefix):
            text = text[len(prefix):].lstrip(' ,，:：')
            break
    text = text.lstrip('/').strip()
    names = '|'.join(sorted(COMMANDS, key=len, reverse=True))
    m = re.fullmatch(r'[aA](' + names + r')(?:\s+(.*))?', text, re.S)
    if m:
        return m[1], (m[2] or '').strip()
    # Compact forms are limited to commands that actually take arguments.
    m = re.fullmatch(r'[aA](猜)(.+)|[aA](一把|再来)(普通|困难)', text, re.S)
    if m:
        return (m[1], m[2].strip()) if m[1] else (m[3], m[4])
    return None


def config_values(config):
    def bounded(key, default, low, high):
        try:
            return max(low, min(high, int(config.get(key, default))))
        except (TypeError, ValueError):
            return default
    return {
        'normal_seconds': bounded('normal_seconds', 600, 60, 3600),
        'hard_seconds': bounded('hard_seconds', 900, 60, 3600),
        'idle_seconds': bounded('idle_seconds', 300, 30, 3600),
        'guess_cooldown': bounded('guess_cooldown', 2, 0, 30),
        'hint_cooldown': bounded('hint_cooldown', 3, 0, 30),
        'recent_window': bounded('recent_window', 30, 0, 500),
        'timeout_concurrency': bounded('timeout_concurrency', 3, 1, 8),
        'draw_strategy': config.get('draw_strategy') if config.get('draw_strategy') in ('question', 'category') else 'question',
    }


def reveal(state):
    c = state['card']
    separator = ' / ' if c['mode'] == '普通' and 'solution_rules' in c else ' + '
    answers = '；或：'.join(dict.fromkeys(separator.join(label(k) for k in r['core']) for r in solution_rules(c)))
    status = {'win': '答对啦！', 'loss': '十次机会用完啦。', 'stop': '本局已结束。',
              'timeout': '本局已超时。'}[state['result']]
    text = (f"【a一把结算】{status}\n{state['mode']}｜猜测 {state['attempts']}/10｜线索 {state['hint']}/9\n"
            f"{c['id']} · {c['title_zh']} ({c['title_en']})\n原题：{c['source']}\n"
            f"答案：{answers}\n\n中文题意（整理版）：\n{c['statement_zh']}\n"
            f"小例子：{c['example']}\n\n中文思路：{c['explanation']}\n复杂度：{c['complexity']}")
    if c.get('editorial'):
        text += '\n官方题解：' + c['editorial']
    text += '\n啾，题可以不会，答案咱们得看明白。\n用 a再来 开下一局。'
    return text


def split_message(text, limit=1400):
    chunks = []
    while len(text) > limit:
        cut = text.rfind('\n', 0, limit)
        if cut < limit // 3:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip('\n')
    if text:
        chunks.append(text)
    return chunks


class Engine:
    def __init__(self, path, cards, config=None, clock=time.time, rng=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS games(umo TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, umo TEXT NOT NULL,
                ended REAL NOT NULL, state TEXT NOT NULL, delivery TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS history_session ON history(umo, ended);
            CREATE TABLE IF NOT EXISTS seen(umo TEXT, event TEXT, created REAL,
                PRIMARY KEY(umo,event));
            CREATE INDEX IF NOT EXISTS seen_created ON seen(created);
            CREATE TABLE IF NOT EXISTS appeals(id INTEGER PRIMARY KEY, umo TEXT,
                sender TEXT, card_id TEXT, note TEXT, created REAL);
        ''')
        # A process could have died after making a network request.
        columns = {r[1] for r in self.db.execute('PRAGMA table_info(appeals)')}
        for name, definition in (('status', "TEXT NOT NULL DEFAULT '待处理'"),
                                 ('resolution', "TEXT NOT NULL DEFAULT ''")):
            if name not in columns:
                self.db.execute(f'ALTER TABLE appeals ADD COLUMN {name} {definition}')
        self.db.execute('CREATE INDEX IF NOT EXISTS appeals_session ON appeals(umo, status, id)')
        self.db.execute("UPDATE history SET delivery='unknown' WHERE delivery IN ('sending','event_pending')")
        self.cards, self.config = cards, config_values(config or {})
        self.clock, self.rng = clock, rng or random.SystemRandom()
        self.last_cleanup = 0

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.execute('ROLLBACK')
            raise
        else:
            self.db.execute('COMMIT')

    def active(self, umo):
        row = self.db.execute('SELECT state FROM games WHERE umo=?', (umo,)).fetchone()
        return json.loads(row['state']) if row else None

    def last(self, umo):
        row = self.db.execute('SELECT state FROM history WHERE umo=? ORDER BY ended DESC,rowid DESC LIMIT 1', (umo,)).fetchone()
        return json.loads(row['state']) if row else None

    def save(self, umo, state):
        self.db.execute('INSERT OR REPLACE INTO games VALUES(?,?)', (umo, json.dumps(state, ensure_ascii=False)))

    def finish(self, umo, state, result, delivery='pending'):
        state['result'] = result
        if delivery == 'event_reply':
            delivery = 'event_pending'
        self.db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?)',
                        (state['id'], umo, self.clock(), json.dumps(state, ensure_ascii=False), delivery))
        self.db.execute('DELETE FROM games WHERE umo=?', (umo,))
        return Settlement(reveal(state), state['id'])

    def offer(self, state, prefix=''):
        self.delivery_result(state['id'], 'event_pending')
        return Settlement(prefix + reveal(state), state['id'])

    def reply_result(self, reply, outcome):
        if isinstance(reply, Settlement):
            self.db.execute("UPDATE history SET delivery=? WHERE id=? AND delivery='event_pending'",
                            (outcome, reply.game_id))

    def audit_guess(self, state, raw, answer, status, charged=False):
        entries = state.setdefault('input_audit', [])
        entries.append({'raw': raw[:180], 'parsed': sorted(answer or []), 'status': status,
                        'charged': charged, 'at': self.clock(), 'matcher_version': MATCHER_VERSION,
                        'card_version': state['card'].get('version', 1)})
        del entries[:-30]

    def expired(self, state, now):
        return now >= min(state['deadline'], state['last_activity'] + state['idle_seconds'])

    def expire(self):
        with self.transaction():
            for row in self.db.execute('SELECT umo,state FROM games').fetchall():
                state = json.loads(row['state'])
                if self.expired(state, self.clock()):
                    self.finish(row['umo'], state, 'timeout')

    def pending(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM history WHERE delivery='pending' ORDER BY ended,rowid LIMIT 100")]

    def claim_delivery(self, game_id):
        return self.db.execute("UPDATE history SET delivery='sending' WHERE id=? AND delivery='pending'", (game_id,)).rowcount == 1

    def delivery_result(self, game_id, result):
        self.db.execute('UPDATE history SET delivery=? WHERE id=?', (result, game_id))

    def handle(self, umo, sender, event_id, action, arg='', admin=False, route=None):
        with self.transaction():
            now = self.clock()
            if event_id:
                inserted = self.db.execute('INSERT OR IGNORE INTO seen VALUES(?,?,?)', (umo, event_id, now)).rowcount
                if not inserted:
                    return []
                if now - self.last_cleanup >= 300:
                    self.db.execute('DELETE FROM seen WHERE created<?', (now - 86400,))
                    self.last_cleanup = now
            state = self.active(umo)
            prefix = []
            if state and self.expired(state, now):
                prefix.append(self.finish(umo, state, 'timeout', 'event_reply'))
                state = None
                if action not in ('一把', '再来', '帮助', '题库状态'):
                    return prefix
            # An offline/unknown timer result is made available at the next game interaction.
            if not state and not prefix and action != '上局':
                row = self.db.execute("SELECT id,state FROM history WHERE umo=? AND delivery IN ('pending','unknown','failed','blocked','event_pending') ORDER BY ended DESC,rowid DESC LIMIT 1", (umo,)).fetchone()
                if row:
                    prefix.append(self.offer(json.loads(row['state']), '上局结算（此前投递未确认）：\n'))
                    if action in ('进度', '题意', '题解', '结束'):
                        return prefix
            response = self._handle(umo, sender, action, arg, admin, route, state, now)
            return prefix + response

    def _handle(self, umo, sender, action, arg, admin, route, state, now):
        if action == '帮助':
            return [HELP]
        if action == '题库状态':
            if not admin:
                return ['此命令仅机器人管理员可用。']
            counts = {m: sum(c['mode'] == m for c in self.cards) for m in ('普通', '困难')}
            snapshot = ''
            if state:
                current = next((c for c in self.cards if c['id'] == state['card']['id']), None)
                old = not current or current.get('version') != state['card'].get('version')
                snapshot = '\n当前对局使用旧题卡快照，新开局使用新版。' if old else '\n当前对局使用当前题卡版本。'
            return [f"a一把 v{PLUGIN_VERSION}｜题库 v{BANK_VERSION}｜判定器 v{MATCHER_VERSION}\n"
                    f"本地题库：普通 {counts['普通']}，困难 {counts['困难']}。运行中无需网络或模型。" + snapshot]
        if action == '上局':
            last = self.last(umo)
            return [self.offer(last)] if last else ['当前会话还没有已结束的对局。']
        if action in ('申诉列表', '处理申诉'):
            if not admin:
                return ['此命令仅机器人管理员可用。']
            if action == '申诉列表':
                if state:
                    return ['本局结束后可查看申诉列表，避免提前透露题号或解法。']
                rows = self.db.execute('SELECT id,card_id,note,status,resolution FROM appeals WHERE umo=? ORDER BY id DESC LIMIT 10', (umo,)).fetchall()
                return ['当前会话最近申诉：\n' + '\n'.join(
                    f"#{r['id']} {r['status']}｜{r['card_id']}｜{r['note'][:160]}\n处理：{r['resolution'][:160] or '待处理'}" for r in rows)] if rows else ['当前会话暂无申诉。']
            match = re.fullmatch(r'(\d+)\s+(通过|驳回|待补充)\s+(.{2,300})', arg, re.S)
            if not match:
                return ['用法：a处理申诉 编号 通过/驳回/待补充 理由（2—300字）。']
            changed = self.db.execute('UPDATE appeals SET status=?,resolution=? WHERE id=? AND umo=?',
                                      (match[2], match[3], int(match[1]), umo)).rowcount
            return ['已记录处理结果；题库答案需经审核更新，不会自动改判历史对局。' if changed else '当前会话未找到该申诉。']
        if action in ('一把', '再来'):
            if state:
                return ['本群已有一局，使用 a进度 查看，或由发起人使用 a结束。']
            last = self.last(umo)
            mode = arg or (last['mode'] if action == '再来' and last else '普通')
            if mode not in ('普通', '困难'):
                return ['模式只有普通和困难，例如：a一把 困难。']
            pool = [c for c in self.cards if c['mode'] == mode]
            recent = [json.loads(r['state'])['card']['id'] for r in self.db.execute(
                'SELECT state FROM history WHERE umo=? ORDER BY ended DESC,rowid DESC LIMIT ?',
                (umo, self.config['recent_window']))]
            fresh = [c for c in pool if c['id'] not in recent]
            while not fresh and recent:
                recent.pop()
                fresh = [c for c in pool if c['id'] not in recent]
            # Question balance is the default; category balance is an explicit option.
            candidates = fresh or pool
            if self.config['draw_strategy'] == 'category':
                groups = {}
                for c in candidates:
                    groups.setdefault(c.get('draw_group', c['solutions'][0][0]), []).append(c)
                card = self.rng.choice(self.rng.choice(list(groups.values())))
            else:
                card = self.rng.choice(candidates)
            seconds = self.config['normal_seconds' if mode == '普通' else 'hard_seconds']
            state = {'id': uuid.uuid4().hex, 'owner': sender, 'mode': mode, 'card': card,
                     'attempts': 0, 'hint': 0, 'guessed': [], 'records': [], 'cooldowns': {},
                     'last_hint': 0, 'created': now, 'deadline': now + seconds,
                     'last_activity': now, 'idle_seconds': self.config['idle_seconds'],
                     'route': route or {}, 'umo': umo}
            self.save(umo, state)
            return [f'【a一把 · {mode}】开局！\n全群共享 10 次机会，最长 {seconds // 60} 分钟。\n'
                    '现在没有题目提示。可以盲猜，也可以用 a提示 领取第一段题意。\n'
                    'a猜 算法名（组合用 +）｜a提示｜a进度｜a结束\n啾，先别急着把算法目录全背一遍。']
        if action == '申诉':
            target = state or self.last(umo)
            if not target or not 5 <= len(arg) <= 1000:
                return ['请在有对局记录时提交 5—1000 字说明：a申诉 你的解法。']
            recent = self.db.execute('SELECT created FROM appeals WHERE umo=? AND sender=? ORDER BY id DESC LIMIT 1', (umo, sender)).fetchone()
            if recent and now - recent['created'] < 60:
                return ['申诉已收到，一分钟内无需重复提交。']
            self.db.execute('INSERT INTO appeals(umo,sender,card_id,note,created) VALUES(?,?,?,?,?)',
                            (umo, sender, target['card']['id'], arg, now))
            return ['已保存解法申诉，供管理员核对；不会让模型临时改答案。']
        if not state:
            last = self.last(umo)
            if action in ('题意', '题解') and last:
                return [self.offer(last)]
            return ['当前没有正在进行的 a一把。用 a一把 或 a一把 困难 开局。']
        if action == '结束':
            if sender != state['owner'] and not admin:
                return ['只有本局发起人或机器人管理员可以结束。']
            return [self.finish(umo, state, 'stop', 'event_reply')]
        if action in ('进度', '题意', '题解'):
            hints = state['card']['hints'][:state['hint']]
            history = '\n'.join(state['records']) or '尚未提交有效答案。'
            return [f"{state['mode']}｜猜测 {state['attempts']}/10｜线索 {state['hint']}/9\n"
                    f"剩余最多 {max(0, int(min(state['deadline'], state['last_activity'] + state['idle_seconds']) - now))} 秒\n"
                    + ('\n'.join(f'{i+1}. {h}' for i, h in enumerate(hints)) or '目前没有题目线索。')
                    + '\n猜测记录：\n' + history + '\n完整答案与链接在结束后公布。']
        if action == '提示':
            if state['hint'] >= 9:
                return ['九层线索已全部给出，请继续猜测或由发起人 a结束。']
            if now - state['last_hint'] < self.config['hint_cooldown']:
                return ['稍等片刻再要提示，这次不扣次数。']
            state['hint'] += 1
            state['last_hint'] = state['last_activity'] = now
            self.save(umo, state)
            return [f"线索 {state['hint']}/9：{state['card']['hints'][state['hint']-1]}\n剩余 {10-state['attempts']} 次猜测。"]
        if action == '猜':
            if now - state['cooldowns'].get(sender, 0) < self.config['guess_cooldown']:
                return ['慢一点，本次不扣次数。']
            answer, error = parse(arg)
            if error:
                self.audit_guess(state, arg, answer, 'clarify')
                self.save(umo, state)
                return [error]
            key = answer_key(answer, state['card'])
            # Normalize legacy keys on comparison as well; no database rewrite.
            if key in {answer_key(old.split('|'), state['card']) for old in state['guessed']}:
                return ['这一套答案已经猜过了，本次不扣次数。']
            state['guessed'].append(key)
            state['attempts'] += 1
            state['cooldowns'][sender] = state['last_activity'] = now
            verdict = assess(state['card'], answer)
            result = verdict.status
            visible = ' + '.join(label(k) for k in sorted(answer))
            feedback = verdict.feedback
            self.audit_guess(state, arg, answer, result, charged=True)
            state['records'].append(f"{state['attempts']}. {visible}：{feedback}")
            if result == 'correct':
                return [self.finish(umo, state, 'win', 'event_reply')]
            if state['attempts'] == 10:
                return [self.finish(umo, state, 'loss', 'event_reply')]
            if state['hint'] < 9:
                state['hint'] += 1
            self.save(umo, state)
            return [f"识别为：{visible}\n{feedback}。剩余 {10-state['attempts']} 次。\n"
                    f"线索 {state['hint']}/9：{state['card']['hints'][state['hint']-1]}"]
        return [HELP]
