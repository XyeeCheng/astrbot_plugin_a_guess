"""Sanitized gameplay regressions: problem IDs and guesses only, no chat IDs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from aguess.bank import load_bank
from aguess.core import Engine
from aguess.matcher import answer_key, assess, judge, parse


class MatchingRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = {c['id']: c for c in load_bank()}

    def check(self, pid, text, expected):
        parsed, error = parse(text)
        self.assertFalse(error, (text, error))
        self.assertEqual(judge(self.cards[pid], parsed), expected, (pid, text))

    def test_binary_names_are_valid_inputs(self):
        for text in ('二分', '二分法', '二分算法', '二分查找', '二分答案',
                     '答案二分', 'binary search', '折半查找', '二分搜索法'):
            with self.subTest(text=text):
                self.check('622A', text, 'correct')

    def test_binary_family_works_in_every_bank_solution(self):
        for c in self.cards.values():
            for solution in c['solutions']:
                if not {'binary_search', 'binary_answer'} & set(solution):
                    continue
                for replacement in ('binary', 'binary_search', 'binary_answer'):
                    answer = frozenset(replacement if k.startswith('binary_') else k
                                       for k in solution)
                    self.assertEqual(judge(c, answer), 'correct', (c['id'], answer))

    def test_binary_is_one_method_not_two(self):
        self.check('846D', '二分 + 二分答案 + 二分查找', 'partial')
        verdict = assess(self.cards['846D'], parse('二分 + 二分答案')[0])
        self.assertEqual((len(verdict.matched), verdict.total), (1, 2))
        self.assertIn('还缺 1 个', verdict.feedback)

    def test_binary_keys_independent_of_hidden_card(self):
        keys = {answer_key(parse(t)[0]) for t in
                ('二分', '二分答案', '二分查找', '二分 + 二分查找')}
        self.assertEqual(keys, {'binary'})

    def test_scanline_aliases_and_suffixes(self):
        for text in ('扫描线', '扫描线算法', '扫描线法', 'scanline',
                     'sweep-line', 'SweepLine', 'scan line', '离线扫描'):
            self.check('612D', text, 'correct')

    def test_natural_connectors_preserve_prefix_sum(self):
        for text in ('二分和二维前缀和', '二分与二维前缀和',
                     '二维前缀和和二分', '二分算法 + 二维前缀和方法'):
            self.check('846D', text, 'correct')
        self.assertEqual(parse('前缀和')[0], frozenset({'prefix'}))
        self.assertEqual(parse('前缀和与枚举')[0], frozenset({'prefix', 'enumeration'}))

    def test_652D_scanline_in_log_is_partial_not_wrong(self):
        for text in ('扫描线', '线段树', '排序', '有序集合', '分治'):
            self.check('652D', text, 'partial')
        feedback = assess(self.cards['652D'], parse('扫描线')[0]).feedback
        self.assertIn('命中 1/2', feedback)
        self.assertIn('扫描线', feedback)
        self.assertNotIn('树状数组', feedback)  # Do not reveal the missing answer.
        self.assertNotIn('线段树', feedback)

    def test_652D_complete_alternatives(self):
        for text in ('扫描线 + 树状数组', '扫描线 + 线段树',
                     '扫描线与平衡树', '排序 + 归并计数', '排序 + 分治',
                     '扫描线 + 排序 + 线段树'):
            self.check('652D', text, 'correct')

    def test_652D_irrelevant_log_guesses_still_fail(self):
        for text in ('滑动窗口', '双指针', '贪心', '动态规划', '前缀和'):
            self.check('652D', text, 'wrong')
        for text in ('排序 + 扫描线', '树状数组 + 线段树',
                     '扫描线 + 树状数组 + 动态规划'):
            self.check('652D', text, 'partial')

    def test_632B_reviewed_alternatives(self):
        for text in ('动态规划', '模拟', '前缀和', '枚举', '前缀和 + 枚举',
                     '动态规划 + 前缀和'):
            self.check('632B', text, 'correct')
        for text in ('贪心', '线性基'):
            self.check('632B', text, 'wrong')

    def test_other_reviewed_log_alternatives(self):
        self.check('873D', '贪心', 'correct')
        self.check('911A', '贪心', 'correct')
        self.check('911A', '双指针', 'correct')

    def test_same_sweep_omission_fixed_in_961E(self):
        self.check('961E', '扫描线', 'partial')
        self.check('961E', '扫描线 + 树状数组', 'correct')
        self.check('961E', '扫描线 + 线段树 + 排序', 'correct')

    def test_valid_helpers_do_not_block_normal_win(self):
        self.check('612D', '扫描线 + 排序 + 差分', 'correct')
        self.check('612D', '排序', 'partial')

    def test_normal_single_core_methods_can_be_combined(self):
        self.check('961B', '前缀和 + 滑动窗口', 'correct')
        self.check('632B', '前缀和 + 枚举 + 动态规划', 'correct')
        self.check('961B', '前缀和 + 贪心', 'partial')

    def test_composite_solutions_are_not_flattened(self):
        self.check('888C', '二分', 'partial')
        self.check('888C', '二分 + 滑动窗口', 'correct')
        self.check('808G', 'DP + 贪心 + KMP', 'partial')

    def test_no_global_sweep_sort_or_binary_divide_equivalence(self):
        for pid, text in [('632C', '扫描线'), ('873D', '二分'),
                          ('678C', '扫描线'), ('678C', '动态规划'),
                          ('678D', '动态规划'), ('911A', '动态规划'),
                          ('1354E', '二分')]:
            self.check(pid, text, 'wrong')

    def test_broad_categories_negations_and_unknowns_still_clarify(self):
        for text in ('树', '图论', '数学', '搜索', '数据结构算法',
                     '不是扫描线', '二分或者贪心', '不存在的算法'):
            self.assertIsNone(parse(text)[0], text)
        for a, b in [('BFS', 'DFS'), ('树状数组', '线段树'), ('差分', '前缀和')]:
            self.assertNotEqual(answer_key(parse(a)[0]), answer_key(parse(b)[0]))

    def test_feedback_distinguishes_missing_and_extra(self):
        missing = assess(self.cards['808G'], parse('DP')[0]).feedback
        extra = assess(self.cards['808G'], parse('DP + KMP + 贪心')[0]).feedback
        self.assertIn('还缺 1 个', missing)
        self.assertIn('另有 1 个', extra)
        self.assertNotIn('还缺', extra)
        self.assertNotIn('KMP', missing.upper())

    def test_bank_rejects_two_names_of_one_family_as_hard_solution(self):
        data = {'questions': copy.deepcopy(list(self.cards.values()))}
        next(c for c in data['questions'] if c['id'] == '846D')['solutions'] = [
            ['binary_answer', 'binary_search']]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'questions.json'
            p.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Repeated algorithm family'):
                load_bank(p)


class GameplayRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'games.sqlite3'
        self.cards = load_bank()
        self.umo = 'test:GroupMessage:regression'
        self.seq = 0
        self.engine = self.make()

    def make(self):
        return Engine(self.path, self.cards, {'guess_cooldown': 0}, clock=lambda: 10000)

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def act(self, action, arg=''):
        self.seq += 1
        return '\n'.join(self.engine.handle(self.umo, 'player', str(self.seq), action, arg))

    def start(self, pid):
        card = next(c for c in self.cards if c['id'] == pid)
        self.act('一把', card['mode'])
        state = self.engine.active(self.umo)
        state['card'] = copy.deepcopy(card)
        self.engine.save(self.umo, state)

    def test_binary_spelling_dedupe_and_full_combo(self):
        self.start('846D')
        self.assertIn('命中 1/2', self.act('猜', '二分'))
        for text in ('二分法', '二分答案', '二分查找', '二分 + 二分查找'):
            self.assertIn('已经猜过', self.act('猜', text))
        self.assertEqual(self.engine.active(self.umo)['attempts'], 1)
        self.assertIn('答对', self.act('猜', '二分 + 二维前缀和'))
        self.assertEqual(self.engine.last(self.umo)['attempts'], 2)

    def test_legacy_binary_dedupe_survives_reload(self):
        self.start('846D')
        state = self.engine.active(self.umo)
        state.update(guessed=['binary_answer'], attempts=1)
        self.engine.save(self.umo, state)
        self.engine.close()
        self.engine = self.make()
        self.assertIn('已经猜过', self.act('猜', '二分'))
        self.assertEqual(self.engine.active(self.umo)['attempts'], 1)
        self.assertIn('答对', self.act('猜', '二分 + 二维前缀和'))

    def test_scanline_partial_and_two_turns_do_not_accumulate(self):
        self.start('652D')
        self.assertIn('命中 1/2', self.act('猜', '线段树'))
        self.assertIn('命中 1/2', self.act('猜', '扫描线'))
        self.assertEqual(self.engine.active(self.umo)['attempts'], 2)
        self.assertIn('答对', self.act('猜', '扫描线 + 线段树'))
        self.assertEqual(self.engine.last(self.umo)['attempts'], 3)

    def test_reviewed_dp_wins_first_attempt(self):
        self.start('632B')
        self.assertIn('答对', self.act('猜', '动态规划'))
        self.assertEqual(self.engine.last(self.umo)['attempts'], 1)

    def test_reload_preserves_older_card_and_deadline(self):
        self.start('652D')
        state = self.engine.active(self.umo)
        state['card'].update(version=1, solutions=[['sort', 'fenwick'], ['sort', 'segment']],
                             optional=[])
        self.engine.save(self.umo, state)
        self.engine.close()
        self.engine = self.make()
        restored = self.engine.active(self.umo)
        self.assertEqual(restored, state)
        self.act('结束')
        self.start('652D')
        self.assertIn('答对', self.act('猜', '扫描线 + 线段树'))


if __name__ == '__main__':
    unittest.main()
