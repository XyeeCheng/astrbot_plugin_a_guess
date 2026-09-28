import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from aguess.bank import load_bank
from aguess.core import Engine, command, config_values, reveal, split_message
from aguess.matcher import parse, judge, label


class GameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'game.sqlite3'
        self.cards = load_bank()
        self.now = 10000
        self.engine = self.make()
        self.seq = 0

    def make(self):
        return Engine(self.path, self.cards, {'guess_cooldown': 0, 'hint_cooldown': 0},
                      clock=lambda: self.now, rng=random.Random(3))

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def act(self, action, arg='', sender='owner', umo='qq:GroupMessage:AbC_12', event=None, admin=False):
        self.seq += 1
        return self.engine.handle(umo, sender, event or str(self.seq), action, arg, admin)

    def start(self, pid='961B'):
        self.act('一把', next(c['mode'] for c in self.cards if c['id'] == pid))
        state = self.engine.active('qq:GroupMessage:AbC_12')
        state['card'] = next(c for c in self.cards if c['id'] == pid)
        self.engine.save('qq:GroupMessage:AbC_12', state)
        return state

    def test_initial_reply_hides_problem(self):
        output = '\n'.join(self.act('一把'))
        card = self.engine.active('qq:GroupMessage:AbC_12')['card']
        for secret in (card['id'], card['title_en'], card['source'], card['hints'][0]):
            self.assertNotIn(secret, output)

    def test_all_cards_solutions_and_hints(self):
        self.assertEqual(len(self.cards), 200)
        self.assertEqual(sum(c['mode'] == '困难' for c in self.cards), 50)
        for c in self.cards:
            with self.subTest(card=c['id']):
                self.assertEqual(len(c['hints']), 9)
                self.assertIn('Educational', c['round'])
                for answer in c['solutions']:
                    parsed, error = parse(' + '.join(label(k) for k in answer))
                    self.assertFalse(error)
                    self.assertEqual(judge(c, parsed), 'correct')

    def test_tenth_correct_wins(self):
        self.start()
        for x in ['贪心','dp','dfs','bfs','dsu','枚举','排序','模拟','构造']:
            self.act('猜', x)
        reply = self.act('猜', 'prefix sum')
        self.assertIn('答对', reply[0])
        self.assertEqual(self.engine.last('qq:GroupMessage:AbC_12')['attempts'], 10)
        self.assertIsNone(self.engine.active('qq:GroupMessage:AbC_12'))

    def test_tenth_wrong_closes_once(self):
        self.start()
        for x in ['贪心','dp','dfs','bfs','dsu','枚举','排序','模拟','构造','二分答案']:
            last = self.act('猜', x)
        self.assertIn('机会用完', last[0])
        self.assertIn('当前没有', self.act('猜', '前缀和')[0])
        self.assertEqual(self.engine.db.execute('SELECT count(*) FROM history').fetchone()[0], 1)

    def test_synonym_duplicate_and_event_redelivery(self):
        self.start()
        self.act('猜','贪心',event='dup')
        self.assertEqual(self.act('猜','贪心',event='dup'), [])
        self.assertIn('已经猜过', self.act('猜','GREEDY')[0])
        self.assertEqual(self.engine.active('qq:GroupMessage:AbC_12')['attempts'], 1)

    def test_invalid_and_ambiguous_dont_spend(self):
        self.start()
        for x in ['', '树', '不是贪心是dp', 'DP或BFS', 'unknown', 'dfs+bfs+dp+greedy']:
            self.act('猜', x)
        self.assertEqual(self.engine.active('qq:GroupMessage:AbC_12')['attempts'], 0)

    def test_hint_independent_bounded_and_no_answer_leak(self):
        self.start()
        for _ in range(12):
            self.act('提示')
        s = self.engine.active('qq:GroupMessage:AbC_12')
        self.assertEqual((s['hint'], s['attempts']), (9,0))
        self.assertNotIn('https://', self.act('题解')[0])

    def test_hard_partial_never_accumulates_win(self):
        self.start('808G')
        self.assertIn('尚未完整', self.act('猜','KMP')[0])
        self.assertIn('尚未完整', self.act('猜','DP')[0])
        self.assertIsNotNone(self.engine.active('qq:GroupMessage:AbC_12'))
        self.assertIn('答对', self.act('猜','DP + kmp')[0])

    def test_wrong_superset_not_accepted(self):
        self.start('808G')
        self.assertNotIn('答对', self.act('猜','KMP + DP + 贪心')[0])

    def test_alternate_solution(self):
        self.start('846D')
        self.assertIn('答对', self.act('猜','滑动窗口 + 单调队列')[0])

    def test_end_permissions(self):
        self.start()
        self.assertIn('只有', self.act('结束', sender='other')[0])
        self.assertIn('结算', self.act('结束', sender='admin', admin=True)[0])

    def test_session_and_platform_isolation(self):
        self.start()
        self.act('一把', umo='another:GroupMessage:AbC_12')
        self.act('猜','贪心')
        self.assertEqual(self.engine.active('another:GroupMessage:AbC_12')['attempts'],0)

    def test_restart_pins_progress_and_card(self):
        state = self.start()
        self.act('猜','贪心')
        self.engine.close()
        self.engine = self.make()
        restored = self.engine.active('qq:GroupMessage:AbC_12')
        self.assertEqual(restored['card']['id'], '961B')
        self.assertEqual(restored['deadline'], state['deadline'])
        self.assertEqual((restored['attempts'], restored['hint']), (1,1))

    def test_timeout_persist_and_next_interaction(self):
        self.start()
        self.now += 301
        self.engine.expire()
        self.assertEqual(len(self.engine.pending()), 1)
        self.engine.expire()
        self.assertEqual(len(self.engine.pending()), 1)
        self.assertIn('超时', self.act('进度')[0])
        self.assertEqual(len(self.engine.pending()), 0)

    def test_old_unknown_never_auto_retried(self):
        self.start()
        self.now += 301
        self.engine.expire()
        p = self.engine.pending()[0]
        self.assertTrue(self.engine.claim_delivery(p['id']))
        self.assertFalse(self.engine.claim_delivery(p['id']))
        self.engine.close()
        self.engine = self.make()
        self.assertEqual(self.engine.pending(), [])
        self.assertIn('此前投递未确认', self.act('进度')[0])

    def test_progress_does_not_extend_idle(self):
        self.start()
        self.now += 200
        self.act('进度')
        self.now += 101
        self.assertIn('超时', self.act('猜','前缀和')[0])

    def test_active_controls_cant_reveal(self):
        self.start('808G')
        for action in ('进度','题意','题解'):
            response=''.join(self.act(action))
            self.assertNotIn('808G',response)
            self.assertNotIn('KMP',response)
            self.assertNotIn('https://',response)

    def test_dedupe_across_connections(self):
        self.start()
        def submit(_):
            e = self.make()
            try:
                return e.handle('qq:GroupMessage:AbC_12','other','parallel','猜','贪心')
            finally:
                e.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(submit,range(2)))
        self.assertEqual(sum(bool(x) for x in responses),1)
        self.assertEqual(self.engine.active('qq:GroupMessage:AbC_12')['attempts'],1)

    def test_all_endings_include_chinese_and_link(self):
        state = self.start()
        for reason in ('win','loss','stop','timeout'):
            out = reveal({**state,'result':reason})
            self.assertIn('中文题意',out)
            self.assertIn('中文思路',out)
            self.assertIn(state['card']['source'],out)

    def test_appeal_bounded_and_private(self):
        self.start()
        self.assertIn('已保存', self.act('申诉','我认为这题还有一种有效解法')[0])
        self.assertIn('无需重复', self.act('申诉','我认为这题还有一种有效解法')[0])

    def test_recent_question_avoidance(self):
        self.act('一把')
        first=self.engine.active('qq:GroupMessage:AbC_12')['card']['id']
        self.act('结束')
        self.act('再来')
        self.assertNotEqual(first,self.engine.active('qq:GroupMessage:AbC_12')['card']['id'])

    def test_cooldowns_dont_spend(self):
        self.engine.config['guess_cooldown']=3
        self.engine.config['hint_cooldown']=3
        self.start()
        self.act('猜','贪心')
        self.act('猜','dp')
        self.act('提示')
        self.act('提示')
        state=self.engine.active('qq:GroupMessage:AbC_12')
        self.assertEqual(state['attempts'],1)
        self.assertEqual(state['hint'],2)


class ParsingTests(unittest.TestCase):
    def test_commands_do_not_capture_friberg(self):
        for text in ('我猜 donk','猜 s1mple','提示','结束','弗一把','随便聊天'):
            self.assertIsNone(command(text))
        self.assertEqual(command('菲比 Ａ一把 困难',['菲比']),('一把','困难'))
        self.assertEqual(command('/a猜 dp + KMP'),('猜','dp + KMP'))

    def test_similar_algorithms_are_distinct(self):
        self.assertNotEqual(parse('BFS')[0],parse('DFS')[0])
        self.assertNotEqual(parse('差分')[0],parse('前缀和')[0])
        self.assertNotEqual(parse('二分答案')[0],parse('二分查找')[0])
        self.assertNotEqual(parse('树状数组')[0],parse('线段树')[0])

    def test_fuzzy_long_spelling(self):
        self.assertEqual(parse('dynmic programming')[0],frozenset({'dp'}))
        self.assertEqual(parse('前辍和')[0],frozenset({'prefix'}))

    def test_combo_does_not_split_chinese_algorithm_names(self):
        self.assertEqual(parse('二分答案 + 二维前缀和')[0],frozenset({'binary_answer','prefix2d'}))
        self.assertEqual(parse('前缀异或 + 01字典树')[0],frozenset({'prefix_xor','trie01'}))

    def test_schema_config_false_zero_and_bounds(self):
        self.assertEqual(config_values({'guess_cooldown':0})['guess_cooldown'],0)
        self.assertEqual(config_values({'normal_seconds':-3})['normal_seconds'],60)

    def test_chunking_preserves_text(self):
        text='中文测试'*1600
        chunks=split_message(text)
        self.assertEqual(''.join(chunks),text)
        self.assertTrue(all(len(x)<=1400 for x in chunks))

    def test_no_empty_mode(self):
        data={'questions':[c for c in load_bank() if c['mode']=='普通']}
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'bank.json'
            p.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(ValueError): load_bank(p)


if __name__ == '__main__':
    unittest.main()
