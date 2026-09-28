"""Answer parsing never consults the hidden answer to correct a player's text."""
import difflib
import re
import unicodedata
from dataclasses import dataclass

ALIASES = {
    'dp': ('动态规划', 'dp', '动规', 'dynamic programming', '线性dp', '线性动态规划'),
    'greedy': ('贪心', 'greedy', '贪心算法'),
    'prefix': ('前缀和', 'prefix sum', 'prefix sums', '前辍和', 'qianzhuihe'),
    'prefix_xor': ('前缀异或', 'prefix xor', '异或前缀和'),
    'window': ('滑动窗口', '定长窗口', '滑窗', '尺取法', 'sliding window'),
    'two_pointers': ('双指针', 'two pointers', 'two pointer'),
    'dsu': ('并查集', 'dsu', 'union find', 'disjoint set union'),
    'dfs': ('深度优先搜索', 'dfs', '深搜', '深度优先遍历'),
    'bfs': ('广度优先搜索', 'bfs', '宽搜', '广搜', '宽度优先搜索'),
    'components': ('连通分量', '连通块', 'connected components'),
    'enumeration': ('枚举', '穷举', '暴力枚举', 'enumeration', 'brute force'),
    'divisors': ('约数枚举', '枚举约数', '根号枚举', '枚举因子', '因数枚举'),
    'count': ('计数', '频次统计', '计数统计', '哈希计数', '计数桶', 'hash counting'),
    'gap': ('最大间隔', '相邻位置差', '间隔统计', '最大间隙'),
    'contribution': ('贡献法', '贡献统计', '统计贡献', 'contribution'),
    'last_position': ('最近出现位置', '最后出现位置', '位置维护'),
    'divide': ('分治', 'divide and conquer', '分治算法'),
    'sort': ('排序', 'sorting', 'sort'),
    'simulation': ('模拟', 'simulation', '字符串解析', '字符串模拟'),
    'construct': ('构造', '构造算法', 'constructive', '蛇形遍历'),
    'binary': ('二分', '二分法', '二分算法'),
    'binary_answer': ('二分答案', 'binary search on answer', '答案二分'),
    'binary_search': ('二分查找', 'binary search', 'upper bound', 'lower bound', '折半查找', '二分搜索'),
    'trie01': ('01字典树', '01trie', '二进制字典树', 'binary trie', '0/1 trie'),
    'kmp': ('kmp', 'kmp自动机', '前缀函数自动机', '字符串匹配自动机'),
    'prefix2d': ('二维前缀和', '2d prefix sum', '二维区间和'),
    'monoque': ('单调队列', 'monotonic queue', '单调双端队列'),
    'factor': ('质因数分解', '素因数分解', '分解质因数', 'prime factorization'),
    'combinatorics': ('组合计数', '组合数学', '隔板法', '排列组合', 'combinatorics'),
    'divisor_sieve': ('约数筛', '因数筛', '约数个数预处理', '筛法求约数个数'),
    'fenwick': ('树状数组', 'bit', 'fenwick', 'fenwick tree'),
    'segment': ('线段树', 'segment tree', '线段树剪枝'),
    'ordered_set': ('有序集合', '平衡树', 'ordered set', 'set', '顺序统计树', '排名树', 'order statistic tree', 'pbds'),
    'inclusion': ('容斥', '容斥原理', 'inclusion exclusion', 'inclusion-exclusion'),
    'bridges': ('桥', '割边', 'tarjan求桥', '边双连通分量', '桥缩点', '求桥'),
    'diameter': ('树的直径', '树直径', 'tree diameter', '直径'),
    'expectation': ('期望', '期望线性性', '概率期望', '线性期望', 'expectation'),
    'merge': ('归并排序', '归并计数', '归并', 'merge sort'),
    'bipartite': ('二分图', '二分图染色', '二染色', 'bipartite coloring'),
    'knapsack': ('背包', '01背包', '0/1背包', '背包dp', 'knapsack'),
    'fast_power': ('快速幂', 'fast power', 'binary exponentiation'),
    'difference': ('差分', 'difference array'),
    'dijkstra': ('dijkstra', '迪杰斯特拉', 'dij'),
    'mst': ('最小生成树', 'kruskal', 'prim', 'mst'),
    'arithmetic': ('公式推导', '数学公式', '等差数列求和', '算术公式'),
    'geometry': ('计算几何', '几何', '极角排序', '叉积', '向量几何'),
    'small_to_large': ('启发式合并', '小并大', 'small to large', 'small-to-large merging'),
    'dsu_on_tree': ('树上启发式合并', 'dsu on tree', 'sack'),
    'lca': ('最近公共祖先', 'lca', '倍增lca'),
    'hld': ('树链剖分', '重链剖分', 'hld', 'heavy light decomposition'),
    'stack': ('栈', 'stack', '括号栈'),
    'sweep': ('扫描线', 'sweep line', '事件扫描', 'scanline', 'scan line', '离线扫描', '扫面线'),
    'quotient_group': ('整除分块', '数论分块', '整除商分块', 'division blocking'),
    'euler': ('DFS序', 'dfn', 'dfs order', '子树展开', '欧拉序'),
    'modular': ('模运算', '取模', '余数分析', '整除性质', 'modular arithmetic'),
    'digit_dp': ('数位DP', '数位动态规划', 'digit dp'),
    'reverse': ('逆向模拟', '倒推', '逆推', '逆序处理', '逆向思维'),
    'parity': ('奇偶分析', '奇偶性', '奇偶性分析', 'parity'),
    'prime_sieve': ('素数筛', '质数筛', '埃氏筛', '欧拉筛', 'prime sieve'),
    'matrix_power': ('矩阵快速幂', '矩阵幂', 'matrix exponentiation'),
    'doubling': ('倍增', '二进制跳跃', 'binary lifting'),
    'median': ('中位数', '下中位数', 'median'),
    'subsequence': ('子序列匹配', '前后缀匹配', '前缀后缀匹配', 'subsequence matching'),
    'bitwise': ('位运算', 'lowbit', '二进制分析', 'bit operations'),
    'sqrt_decomp': ('根号分治', '根号分解', '分块', 'sqrt decomposition'),
    'mobius': ('莫比乌斯反演', '莫比乌斯函数', 'mobius inversion'),
    'monostack': ('单调栈', 'monotonic stack'),
    'topo': ('拓扑排序', 'topological sort', 'toposort', 'kahn'),
    'heap': ('堆', '优先队列', '最小堆', '最大堆', 'heap', 'priority queue'),
    'xor_basis': ('线性基', '异或线性基', 'xor basis', 'linear basis'),
    'cycle': ('循环节', '周期检测', '找环', 'cycle detection'),
    'meet_middle': ('折半搜索', '折半枚举', '中途相遇', 'meet in the middle', 'mitm'),
    'case_analysis': ('分类讨论', '分类枚举', 'case analysis'),
    'backtracking': ('回溯', '回溯搜索', 'backtracking'),
    'gcd': ('欧几里得算法', '辗转相除', '辗转相除法', 'gcd', 'euclidean algorithm'),
    'bitmask': ('子集枚举', '二进制枚举', '枚举子集', 'bitmask enumeration'),
    'discretize': ('离散化', '坐标压缩', 'coordinate compression'),
    'tree_dp': ('树形DP', '树上DP', '树形动态规划', 'tree dp'),
    'interval_dp': ('区间DP', '区间动态规划', 'interval dp'),
    'memo': ('记忆化搜索', '记忆化', 'memoization', 'memoisation'),
    'shortest_path': ('最短路', '最短路径', 'shortest path'),
    'trie': ('字典树', 'trie', '前缀树'),
    'group_knapsack': ('分组背包', '分组背包DP', 'group knapsack'),
}


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold().strip()
    return re.sub(r'[\s_\-]+', '', text)


LOOKUP = {normalize(alias): key for key, aliases in ALIASES.items() for alias in aliases}
AMBIGUOUS = {'树', '搜索', '图论', '数据结构', '数学', '优化', 'tarjan'}

# This game accepts the binary-search family at either level of specificity.
# Keep the original IDs for card explanations and existing database snapshots.
# Never globally equate sweep/sort, BFS/DFS, or unrelated data structures.
FAMILIES = {'binary_answer': 'binary', 'binary_search': 'binary'}


def canonical(methods, card=None):
    aliases = (card or {}).get('method_aliases', {})
    return frozenset(FAMILIES.get(aliases.get(k, k), aliases.get(k, k)) for k in methods)


def answer_key(methods, card=None):
    """Apply the same reviewed normalization to judging and duplicate answers."""
    return '|'.join(sorted(canonical(methods, card)))


def solution_rules(card):
    return card.get('solution_rules') or [
        {'core': s, 'helpers': []} for s in card['solutions']]


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(nxt[-1] + 1, row[j] + 1, row[j-1] + (x != y)))
        row = nxt
    return row[-1]


def label(key):
    return ALIASES[key][0]


def _token(part):
    token = normalize(part)
    if token in LOOKUP or token in AMBIGUOUS:
        return token
    # Only remove a wrapper if the remaining name is already known.
    for suffix in ('算法', '方法', '法'):
        if token.endswith(suffix):
            stem = token[:-len(suffix)]
            if stem in LOOKUP or stem in AMBIGUOUS:
                return stem
    return token


def _split_natural(part):
    """Recognize 和/与 only between names; 前缀和 stays a single algorithm."""
    if _token(part) in LOOKUP:
        return [part]
    for i, ch in enumerate(part):
        if ch in '和与' and _token(part[:i]) in LOOKUP and part[i+1:].strip():
            return [part[:i], *_split_natural(part[i+1:])]
    return [part]


def parse(text):
    """Return a canonical set or a clarification, without spending an attempt."""
    text = unicodedata.normalize('NFKC', text).strip().strip('。.!！?？;；').strip()
    if not text or len(text) > 180:
        return None, '请提交简短算法名，例如：a猜 前缀和。'
    if re.search(r'或者|(?<!异)或|还是|不是|不要|不用|不使用|不考虑|不选|不能|无需|排除|非'
                 r'|\b(?:or|not|no|without|except|exclude|neither|nor|cannot)\b|n[\x27’]t\b'
                 r'|\b(?:no|not)(?=[a-z])', text, re.I):
        return None, '一次请明确提交一套解法，用 + 连接，不要列备选或否定句。'
    parts = re.split(r'\s*(?:\+|＋|、|，|,|以及|然后|配合|结合|搭配)\s*', text)
    # Do not split a canonical algorithm name such as 前缀和 or 组合数学.
    if normalize(text) in LOOKUP:
        parts = [text]
    parts = [piece for part in parts for piece in _split_natural(part)]
    if len(parts) > 3 or any(not x for x in parts):
        return None, '每次提交 1—3 个核心方法，用 + 连接。'
    result = set()
    for part in parts:
        token = _token(part)
        if token in LOOKUP:
            result.add(LOOKUP[token])
            continue
        if token in AMBIGUOUS:
            return None, f'“{part}”较宽泛，请写具体方法；本次不扣次数。'
        # Short acronyms (BFS/DFS/BIT/DP) are deliberately never fuzzy corrected.
        if len(token) >= 5 and re.fullmatch(r'[a-z][a-z0-9 ]*', part.casefold().strip()):
            matches = [(difflib.SequenceMatcher(None, token, a).ratio(), k)
                       for a, k in LOOKUP.items() if len(a) >= 5
                       and abs(len(a) - len(token)) <= 2 and edit_distance(token, a) <= 2]
            matches.sort(reverse=True)
            if matches and matches[0][0] >= .86:
                candidates = {k for score, k in matches if score >= matches[0][0] - .035}
                if len(candidates) == 1:
                    result.add(matches[0][1])
                    continue
        return None, f'暂未识别“{part}”，请换用完整中英文算法名；本次不扣次数。'
    return frozenset(result), ''


@dataclass(frozen=True)
class Verdict:
    status: str
    matched: frozenset
    total: int
    extra: int

    @property
    def feedback(self):
        if self.status == 'correct':
            return '正确'
        if self.status == 'wrong':
            return '未命中已收录解法；若有其他思路可用 a申诉 提交说明'
        names = ' + '.join(label(k) for k in sorted(self.matched))
        text = f'命中 {len(self.matched)}/{self.total} 个核心方法（{names}）'
        missing = self.total - len(self.matched)
        if missing:
            text += f'；组合尚未完整，还缺 {missing} 个，请用 + 一次提交完整组合'
        if self.extra:
            text += f'；另有 {self.extra} 个方法不属于这一套已收录解法'
        return text


def assess(card, answer):
    answer = canonical(answer, card)
    allowed = canonical(card.get('optional', []), card)
    rules = solution_rules(card)
    normal = card.get('mode') == '普通' and 'solution_rules' in card
    if card.get('mode') == '普通':
        # Only explicitly reviewed cores are eligible for single-method wins.
        allowed |= canonical((k for r in rules if normal or len(r['core']) == 1 for k in r['core']), card)
    candidates = []
    for rule in rules:
        required = canonical(rule['core'], card)
        matched = required & answer
        extra = len(answer - required - allowed - canonical(rule.get('helpers', []), card))
        complete = bool(matched) if normal else matched == required
        status = ('correct' if complete and not extra
                  else 'partial' if matched else 'wrong')
        if normal:
            matched = frozenset(sorted(matched)[:1])
        candidates.append(Verdict(status, matched, 1 if normal else len(required), extra))
    return max(candidates, key=lambda v: (v.status == 'correct', len(v.matched),
                                         -v.extra, -v.total))


def judge(card, answer):
    return assess(card, answer).status
