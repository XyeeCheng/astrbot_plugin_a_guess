import json
from pathlib import Path
from .matcher import ALIASES, canonical


def load_bank(path=None):
    path = Path(path) if path else Path(__file__).parent.parent / 'questions.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    cards = data['questions']
    seen = set()
    for card in cards:
        pid = card['id']
        if pid in seen:
            raise ValueError(f'Duplicate card: {pid}')
        seen.add(pid)
        if card['mode'] not in ('普通', '困难') or len(card['hints']) != 9:
            raise ValueError(f'Invalid mode/hints: {pid}')
        if not card['solutions'] or not all(card['hints']):
            raise ValueError(f'Empty card: {pid}')
        for solution in card['solutions']:
            if not solution or len(solution) != len(set(solution)):
                raise ValueError(f'Invalid solution: {pid}')
            if card['mode'] == '困难' and not 2 <= len(solution) <= 3:
                raise ValueError(f'Hard solution must be a combination: {pid}')
            if not set(solution) <= ALIASES.keys():
                raise ValueError(f'Unknown algorithm: {pid}')
            if len(canonical(solution)) != len(solution):
                raise ValueError(f'Repeated algorithm family in solution: {pid}')
        if not set(card.get('optional', [])) <= ALIASES.keys():
            raise ValueError(f'Unknown optional algorithm: {pid}')
        aliases = card.get('method_aliases', {})
        if not isinstance(aliases, dict) or not set(aliases) <= ALIASES.keys() or not set(aliases.values()) <= ALIASES.keys():
            raise ValueError(f'Invalid method aliases: {pid}')
        if any(target in aliases for target in aliases.values()):
            raise ValueError(f'Chained method aliases: {pid}')
        rules = card.get('solution_rules')
        if rules is not None:
            if len(rules) != len(card['solutions']):
                raise ValueError(f'Rules/solutions mismatch: {pid}')
            for rule, solution in zip(rules, card['solutions']):
                core, helpers = rule['core'], rule.get('helpers', [])
                if not core or set(core) & set(helpers) or set(core + helpers) != set(solution):
                    raise ValueError(f'Invalid core/helpers: {pid}')
                if len(canonical(core, card)) != len(core):
                    raise ValueError(f'Repeated core concept: {pid}')
                if card['mode'] == '困难' and len(core) < 2:
                    raise ValueError(f'Hard rules need multiple cores: {pid}')
        if card.get('draw_group', card['solutions'][0][0]) not in ALIASES:
            raise ValueError(f'Invalid draw group: {pid}')
        for field in ('statement_zh', 'explanation', 'complexity', 'example', 'source', 'round'):
            if not card.get(field):
                raise ValueError(f'Missing {field}: {pid}')
        if not card['source'].startswith('https://codeforces.com/'):
            raise ValueError(f'Untrusted source: {pid}')
    if not all(any(c['mode'] == m for c in cards) for m in ('普通', '困难')):
        raise ValueError('Both difficulty modes require cards')
    return cards
