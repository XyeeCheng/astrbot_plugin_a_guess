"""Whole-bank gameplay checks and alias-boundary regressions."""
import json
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from aguess.bank import load_bank
from aguess.core import Engine
from aguess.matcher import ALIASES, normalize, parse, judge, label


class ExpandedBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = load_bank()

    def test_200_unique_complete_cards(self):
        self.assertEqual(len({c['id'] for c in self.cards}), 200)
        root=Path(__file__).resolve().parents[1]
        audit=json.loads((root/'docs/SOURCE_AUDIT.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['questions_file_sha256'],hashlib.sha256((root/'questions.json').read_bytes()).hexdigest())
        self.assertEqual({x['id'] for x in audit['cards']},{c['id'] for c in self.cards})
        hashes={x['id']:x['card_sha256'] for x in audit['cards']}
        for c in self.cards:
            with self.subTest(card=c['id']):
                self.assertEqual(hashes[c['id']],hashlib.sha256(json.dumps(c,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
                pid=re.fullmatch(r'(\d+)([A-Z]\d?)',c['id'])
                self.assertIsNotNone(pid)
                self.assertEqual(c['source'],f'https://codeforces.com/contest/{pid[1]}/problem/{pid[2]}')
                self.assertIn('Educational',c['round'])
                for key in ('title_zh','title_en','example','explanation','complexity','statement_zh'):
                    self.assertTrue(c[key].strip())
                self.assertTrue(re.search(r'[\u4e00-\u9fff]',c['statement_zh']))
                self.assertEqual(len(set(c['hints'])),9)
                self.assertFalse(any('https://' in h for h in c['hints'][:5]))

    def test_normal_accepts_a_core_method(self):
        normal=[c for c in self.cards if c['mode']=='普通']
        self.assertEqual(len(normal),150)
        for c in normal:
            self.assertTrue(any(len(s)==1 for s in c['solutions']),c['id'])

    def test_hard_needs_complete_combination(self):
        for c in self.cards:
            if c['mode']!='困难': continue
            for solution in c['solutions']:
                self.assertGreaterEqual(len(solution),2)
                for part in solution:
                    self.assertNotEqual(judge(c,frozenset([part])),'correct',c['id'])

    def test_every_alias_roundtrips_without_collisions(self):
        seen={}
        for key,aliases in ALIASES.items():
            for alias in aliases:
                with self.subTest(key=key,alias=alias):
                    token=normalize(alias)
                    self.assertIn(seen.get(token,key),(key,))
                    seen[token]=key
                    result,error=parse(alias)
                    self.assertEqual(error,'')
                    self.assertEqual(result,frozenset([key]))

    def test_new_neighbor_algorithms_remain_distinct(self):
        for a,b in [('栈','单调栈'),('DFS序','DFS'),('数位DP','DP'),
                    ('素数筛','约数筛'),('矩阵快速幂','快速幂'),('线性基','线段树')]:
            self.assertNotEqual(parse(a)[0],parse(b)[0])

    def test_all_200_can_start_hint_and_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=Engine(Path(tmp)/'bank.sqlite3',self.cards,{'hint_cooldown':0,'guess_cooldown':0})
            try:
                for card in self.cards:
                    umo='test:GroupMessage:'+card['id']
                    opening=engine.handle(umo,'player','open','一把',card['mode'])[0]
                    state=engine.active(umo)
                    self.assertNotIn(state['card']['id'],opening)
                    self.assertNotIn('https://',opening)
                    state['card']=card
                    engine.save(umo,state)
                    for i in range(1,10):
                        out=engine.handle(umo,'player',f'h{i}','提示')[0]
                        self.assertIn(f'线索 {i}/9',out)
                        self.assertNotIn(card['source'],out)
                    text=' + '.join(label(x) for x in card['solutions'][0])
                    out='\n'.join(engine.handle(umo,'player','answer','猜',text))
                    self.assertIn('答对',out,card['id'])
                    self.assertIn(card['source'],out)
                    self.assertIn(card['statement_zh'],out)
                    self.assertIsNone(engine.active(umo))
                self.assertEqual(engine.db.execute('SELECT count(*) FROM history').fetchone()[0],200)
            finally:
                engine.close()


if __name__=='__main__': unittest.main()
