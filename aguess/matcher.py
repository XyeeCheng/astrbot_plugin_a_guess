"""Answer parsing never consults the hidden answer to correct a player's text."""
import difflib
import re
import unicodedata

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
    'binary_answer': ('二分答案', 'binary search on answer', '答案二分'),
    'binary_search': ('二分查找', 'binary search', 'upper bound', 'lower bound'),
    'trie01': ('01字典树', '01trie', '二进制字典树', 'binary trie', '0/1 trie'),
    'kmp': ('kmp', 'kmp自动机', '前缀函数自动机', '字符串匹配自动机'),
    'prefix2d': ('二维前缀和', '2d prefix sum', '二维区间和'),
    'monoque': ('单调队列', 'monotonic queue', '单调双端队列'),
    'factor': ('质因数分解', '素因数分解', '分解质因数', 'prime factorization'),
    'combinatorics': ('组合计数', '组合数学', '隔板法', '排列组合', 'combinatorics'),
    'divisor_sieve': ('约数筛', '因数筛', '约数个数预处理', '筛法求约数个数'),
    'fenwick': ('树状数组', 'bit', 'fenwick', 'fenwick tree'),
    'segment': ('线段树', 'segment tree', '线段树剪枝'),
    'ordered_set': ('有序集合', '平衡树', 'ordered set', 'set'),
    'inclusion': ('容斥', '容斥原理', 'inclusion exclusion', 'inclusion-exclusion'),
    'bridges': ('桥', '割边', 'tarjan求桥', '边双连通分量', '桥缩点', '求桥'),
    'diameter': ('树的直径', '树直径', 'tree diameter', '直径'),
    'expectation': ('期望', '期望线性性', '概率期望', '线性期望', 'expectation'),
    'merge': ('归并排序', '归并计数', 'merge sort'),
    'bipartite': ('二分图', '二分图染色', '二染色', 'bipartite coloring'),
    'knapsack': ('背包', '01背包', '0/1背包', '背包dp', 'knapsack'),
    'fast_power': ('快速幂', '矩阵快速幂', 'fast power'),
    'difference': ('差分', 'difference array'),
    'dijkstra': ('dijkstra', '迪杰斯特拉', 'dij'),
    'mst': ('最小生成树', 'kruskal', 'prim', 'mst'),
}


def normalize(text):
    text = unicodedata.normalize('NFKC', text).casefold().strip()
    return re.sub(r'[\s_\-]+', '', text)


LOOKUP = {normalize(alias): key for key, aliases in ALIASES.items() for alias in aliases}
AMBIGUOUS = {'二分', '树', '搜索', '图论', '数据结构', '数学', '优化', 'trie', '字典树', 'tarjan'}


def label(key):
    return ALIASES[key][0]


def parse(text):
    """Return a canonical set or a clarification, without spending an attempt."""
    text = unicodedata.normalize('NFKC', text).strip()
    if not text or len(text) > 180:
        return None, '请提交简短算法名，例如：a猜 前缀和。'
    if re.search(r'或者|(?<!异)或|还是|\bor\b|不是|不要|排除|不选', text, re.I):
        return None, '一次请明确提交一套解法，用 + 连接，不要列备选或否定句。'
    parts = re.split(r'\s*(?:\+|＋|、|，|,|以及|然后|配合|结合|搭配)\s*', text)
    # Do not split a canonical algorithm name such as 前缀和 or 组合数学.
    if normalize(text) in LOOKUP:
        parts = [text]
    if len(parts) > 3 or any(not x for x in parts):
        return None, '每次提交 1—3 个核心方法，用 + 连接。'
    result = set()
    for part in parts:
        token = normalize(part)
        if token in LOOKUP:
            result.add(LOOKUP[token])
            continue
        if token in AMBIGUOUS:
            return None, f'“{part}”较宽泛，请写具体方法；本次不扣次数。'
        # Short acronyms (BFS/DFS/BIT/DP) are deliberately never fuzzy corrected.
        if len(token) >= 5:
            matches = [(difflib.SequenceMatcher(None, token, a).ratio(), k)
                       for a, k in LOOKUP.items() if len(a) >= 5]
            matches.sort(reverse=True)
            if matches and matches[0][0] >= .86:
                candidates = {k for score, k in matches if score >= matches[0][0] - .035}
                if len(candidates) == 1:
                    result.add(matches[0][1])
                    continue
        return None, f'暂未识别“{part}”，请换用完整中英文算法名；本次不扣次数。'
    return frozenset(result), ''


def judge(card, answer):
    allowed = set(card.get('optional', []))
    for solution in card['solutions']:
        required = set(solution)
        if required <= answer and answer <= required | allowed:
            return 'correct'
    if any(set(s) & answer for s in card['solutions']):
        return 'partial'
    return 'wrong'
