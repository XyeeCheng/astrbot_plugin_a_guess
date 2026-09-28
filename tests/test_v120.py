"""Regressions for reviewed rule granularity and durable settlement recovery."""
import copy
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from aguess.bank import load_bank
from aguess.core import Engine, Settlement, command, config_values
from aguess.matcher import answer_key, judge, parse


class InputRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = {c['id']: c for c in load_bank()}

    def status(self, pid, text):
        answer, error = parse(text)
        self.assertFalse(error, (pid, text, error))
        return judge(self.cards[pid], answer)

    def test_negative_language_is_never_a_positive_guess(self):
        for text in ('not binary search', '不用binary search', '不使用 segment tree',
                     'no binary search', 'without dynamic programming', '不是扫描线',
                     'exclude greedy', "isn't binary search", 'neither bfs nor dfs'):
            self.assertIsNone(parse(text)[0], text)

    def test_punctuation_and_real_spelling_errors(self):
        for text in ('扫描线。', '扫描线！', '扫描线?', 'scanline.', '扫面线'):
            self.assertEqual(self.status('612D', text), 'correct')
        self.assertEqual(self.status('622A', 'binnary search'), 'correct')
        self.assertIsNone(parse('nobinary search')[0])
        self.assertNotEqual(parse('BFS')[0], parse('DFS')[0])

    def test_compact_commands_and_wake_punctuation(self):
        for text, expected in [('a猜二分', ('猜', '二分')), ('a一把困难', ('一把', '困难')),
                               ('菲比，a猜 二分', ('猜', '二分')), ('啾比：a再来普通', ('再来', '普通'))]:
            self.assertEqual(command(text, ['菲比', '啾比']), expected)
        for text in ('猜二分', '提示', 'a一把真的有意思', 'a结束了吗', 'a进度条'):
            self.assertIsNone(command(text))

    def test_reviewed_normal_binary_cores(self):
        for pid in ('1354B', '888C'):
            for text in ('二分', '二分答案', 'binary search'):
                self.assertEqual(self.status(pid, text), 'correct')
        self.assertEqual(self.status('1354B', '二分 + 前缀和'), 'correct')
        self.assertEqual(self.status('612D', '排序'), 'wrong')
        self.assertEqual(self.status('612D', '差分 + 排序'), 'correct')

    def test_per_card_granularity_and_helpers(self):
        for pid, text in [('946D', '滑动窗口 + DP'), ('1354E', '二分图 + DP'),
                          ('846D', '二分 + 前缀和'), ('938D', '最短路'),
                          ('598E', '区间DP + 枚举'), ('710E', '记忆化搜索'),
                          ('652D', '扫描线 + 树状数组 + 离散化')]:
            self.assertEqual(self.status(pid, text), 'correct', (pid, text))
        for text in ('树形DP', '区间DP', '记忆化搜索', '最短路', '字典树'):
            self.assertFalse(parse(text)[1], text)

    def test_no_global_dp_or_prefix_equivalence(self):
        self.assertEqual(self.status('652D', 'DP'), 'wrong')
        self.assertEqual(self.status('961B', '树形DP'), 'wrong')
        self.assertEqual(self.status('846D', '二分 + DP'), 'partial')
        self.assertEqual(self.status('946D', 'DP + 分组背包'), 'partial')
        self.assertEqual(self.status('946D', '滑动窗口 + DP + 贪心'), 'partial')

    def test_every_trie_card_accepts_reviewed_short_name(self):
        cards = [c for c in self.cards.values() if c.get('method_aliases', {}).get('trie') == 'trie01']
        self.assertTrue(cards)
        for card in cards:
            for solution in card['solutions']:
                if 'trie01' in solution:
                    answer = frozenset('trie' if k == 'trie01' else k for k in solution)
                    self.assertEqual(judge(card, answer), 'correct')

    def test_per_card_aliases_share_duplicate_key(self):
        c = self.cards['946D']
        self.assertEqual(answer_key(parse('DP')[0], c), answer_key(parse('分组背包')[0], c))
        self.assertNotEqual(answer_key(parse('DP')[0]), answer_key(parse('分组背包')[0]))

    def test_all_normal_core_entries_win_without_helpers(self):
        for card in self.cards.values():
            if card['mode'] == '普通':
                for rule in card['solution_rules']:
                    for core in rule['core']:
                        self.assertEqual(judge(card, {core}), 'correct', (card['id'], core))

    def test_all_hard_rules_need_more_than_one_concept(self):
        for card in self.cards.values():
            if card['mode'] == '困难':
                for rule in card['solution_rules']:
                    for core in rule['core']:
                        self.assertNotEqual(judge(card, {core}), 'correct', (card['id'], core))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        self.cards = load_bank()
        self.now, self.seq = 10000, 0
        self.umo = 'fixture:GroupMessage:a'
        self.engine = self.make()

    def make(self, **kwargs):
        return Engine(self.path, self.cards, {'guess_cooldown': 0, **kwargs},
                      clock=lambda: self.now, rng=random.Random(7))

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def act(self, action, arg='', ack=True, umo=None, admin=False):
        self.seq += 1
        replies = self.engine.handle(umo or self.umo, 'owner', str(self.seq), action, arg, admin)
        if ack:
            for reply in replies:
                self.engine.reply_result(reply, 'event_reply')
        return replies

    def start(self, pid='1354B'):
        c = next(c for c in self.cards if c['id'] == pid)
        self.act('一把', c['mode'])
        state = self.engine.active(self.umo)
        state['card'] = copy.deepcopy(c)
        self.engine.save(self.umo, state)
        return state

    def delivery(self):
        return self.engine.db.execute('SELECT delivery FROM history ORDER BY rowid DESC LIMIT 1').fetchone()[0]

    def test_uncertain_event_then_new_round_keeps_last_accessible(self):
        self.start()
        reply = self.act('结束', ack=False)[0]
        self.assertIsInstance(reply, Settlement)
        self.assertEqual(self.delivery(), 'event_pending')
        self.engine.reply_result(reply, 'unknown')
        response = self.act('再来')
        self.assertIn('此前投递未确认', response[0])
        active = self.engine.active(self.umo)
        self.assertIn('1354B', self.act('上局')[0])
        self.assertEqual(self.engine.active(self.umo), active)
        self.assertEqual(self.delivery(), 'event_reply')
        self.assertNotIn('1354B', ''.join(self.act('进度')))

    def test_restart_event_pending_is_unknown_and_recoverable(self):
        self.start()
        self.act('结束', ack=False)
        self.engine.close()
        self.engine = self.make()
        self.assertEqual(self.delivery(), 'unknown')
        self.assertFalse(self.engine.pending())
        self.assertIn('此前投递未确认', self.act('进度')[0])
        self.assertEqual(self.delivery(), 'event_reply')
        self.assertIn('当前没有', self.act('进度')[0])

    def test_last_is_scoped_to_session(self):
        self.start()
        self.act('结束')
        self.assertNotIn('1354B', self.act('上局', umo='fixture:GroupMessage:b')[0])

    def test_raw_input_audit_is_bounded_and_does_not_extend_idle(self):
        original = self.start()
        self.now += 10
        for _ in range(35):
            self.act('猜', '不用binary search')
        state = self.engine.active(self.umo)
        self.assertEqual(state['attempts'], 0)
        self.assertEqual(state['last_activity'], original['last_activity'])
        self.assertEqual(len(state['input_audit']), 30)
        self.assertEqual(state['input_audit'][-1]['raw'], '不用binary search')
        self.assertEqual(state['input_audit'][-1]['matcher_version'], '2')
        self.act('猜', '二分')
        audit = self.engine.last(self.umo)['input_audit'][-1]
        self.assertEqual((audit['status'], audit['charged']), ('correct', True))

    def test_old_snapshot_retains_old_combo_policy(self):
        state = self.start('888C')
        for key in ('solution_rules', 'method_aliases'):
            state['card'].pop(key, None)
        state['card']['version'] = 1
        self.engine.save(self.umo, state)
        self.engine.close()
        self.engine = self.make()
        self.assertIn('旧题卡快照', self.act('题库状态', admin=True)[0])
        self.assertIn('还缺 1 个', self.act('猜', '二分')[0])
        self.assertIn('答对', self.act('猜', '二分 + 滑动窗口')[0])

    def test_version_command_has_no_current_answer(self):
        self.start()
        text = self.act('题库状态', admin=True)[0]
        self.assertIn('v1.2.0', text)
        self.assertIn('普通 150，困难 50', text)
        self.assertNotIn('1354B', text)
        self.assertIn('仅机器人管理员', self.act('题库状态')[0])

    def test_appeal_admin_scope_and_no_active_spoilers(self):
        self.start()
        self.act('申诉', '可以使用二分答案来判断长度')
        self.assertIn('仅机器人管理员', self.act('申诉列表')[0])
        self.assertNotIn('1354B', self.act('申诉列表', admin=True)[0])
        self.act('结束')
        self.assertIn('待处理', self.act('申诉列表', admin=True)[0])
        self.assertIn('未找到', self.act('处理申诉', '1 通过 解法有效', admin=True, umo='another')[0])
        self.assertIn('仅机器人管理员', self.act('处理申诉', '1 通过 解法有效')[0])
        self.assertIn('已记录', self.act('处理申诉', '1 通过 解法有效', admin=True)[0])
        self.assertIn('解法有效', self.act('申诉列表', admin=True)[0])
        self.assertEqual(self.engine.last(self.umo)['result'], 'stop')

    def test_old_appeal_schema_migrates_without_losing_entries(self):
        self.engine.close()
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE appeals')
            db.execute('CREATE TABLE appeals(id INTEGER PRIMARY KEY, umo TEXT, sender TEXT, card_id TEXT, note TEXT, created REAL)')
            db.execute("INSERT INTO appeals VALUES(1,'fixture','owner','1354B','legacy explanation',1)")
        db.close()
        self.engine = self.make()
        row = self.engine.db.execute('SELECT * FROM appeals WHERE id=1').fetchone()
        self.assertEqual((row['note'], row['status'], row['resolution']), ('legacy explanation', '待处理', ''))

    def test_draw_strategy_is_explicit_and_not_solution_order(self):
        class Capture:
            def __init__(self): self.sizes = []
            def choice(self, values):
                self.sizes.append(len(values))
                return values[0]
        cards = copy.deepcopy(self.cards[:3])
        for c, group in zip(cards, ('dp', 'dp', 'greedy')):
            c['mode'], c['draw_group'] = '普通', group
        self.engine.cards = cards
        rng = self.engine.rng = Capture()
        self.act('一把')
        self.assertEqual(rng.sizes, [3])
        self.act('结束')
        self.engine.config.update(draw_strategy='category', recent_window=0)
        rng.sizes.clear()
        self.act('一把')
        self.assertEqual(rng.sizes, [2, 2])
        self.assertEqual(config_values({'draw_strategy': 'invalid'})['draw_strategy'], 'question')


if __name__ == '__main__':
    unittest.main()
