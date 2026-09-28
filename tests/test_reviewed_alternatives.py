"""Independent small-case oracles for the newly accepted solution descriptions."""
import itertools
import random
import unittest


class Fenwick:
    def __init__(self, n):
        self.tree = [0] * (n + 1)

    def add(self, x):
        while x < len(self.tree):
            self.tree[x] += 1
            x += x & -x

    def prefix(self, x):
        result = 0
        while x > 0:
            result += self.tree[x]
            x -= x & -x
        return result


class RankedTreap:
    """Size-augmented randomized BST, not std::set + linear distance."""
    def __init__(self):
        self.root = None
        self.rng = random.Random(652)

    @staticmethod
    def size(node):
        return node[4] if node else 0

    def fix(self, node):
        node[4] = 1 + self.size(node[2]) + self.size(node[3])
        return node

    def insert(self, node, key):
        if node is None:
            return [key, self.rng.random(), None, None, 1]
        side = 2 if key < node[0] else 3
        node[side] = self.insert(node[side], key)
        if node[side][1] < node[1]:
            child = node[side]
            other = 5 - side
            node[side] = child[other]
            child[other] = self.fix(node)
            node = child
        return self.fix(node)

    def add(self, key):
        self.root = self.insert(self.root, key)

    def rank(self, key):
        node, result = self.root, 0
        while node:
            if key <= node[0]:
                node = node[2]
            else:
                result += self.size(node[2]) + 1
                node = node[3]
        return result


class ReviewedAlternativeOracles(unittest.TestCase):
    def test_632B_two_phase_dp_and_incremental_simulation(self):
        def dp(values, teams):
            flipping = stopped = 0
            for value, team in zip(values, teams):
                original = value if team == 'B' else 0
                flipped = value if team == 'A' else 0
                flipping, stopped = flipping + flipped, max(flipping, stopped) + original
            return max(flipping, stopped)

        def simulate(values, teams):
            total = best = sum(v for v, t in zip(values, teams) if t == 'B')
            for value, team in zip(values, teams):
                total += value if team == 'A' else -value
                best = max(best, total)
            return best

        for n in range(1, 6):
            for values in itertools.product((1, 2, 5), repeat=n):
                for teams in itertools.product('AB', repeat=n):
                    brute = sum(v for v, t in zip(values, teams) if t == 'B')
                    for cut in range(n + 1):
                        for flip_prefix in (True, False):
                            score = sum(v for i, (v, t) in enumerate(zip(values, teams))
                                        if (t == 'B') ^ ((i < cut) == flip_prefix))
                            brute = max(brute, score)
                    for method in (dp, simulate):
                        actual = max(method(values, teams), method(values[::-1], teams[::-1]))
                        self.assertEqual(actual, brute, (values, teams, method.__name__))

    def test_652D_sweep_and_merge_count_against_all_pairs(self):
        rng = random.Random(652)
        for _ in range(350):
            n = rng.randint(1, 32)
            coords = rng.sample(range(-1000, 1000), 2 * n)
            segments = [tuple(sorted(coords[2*i:2*i+2])) for i in range(n)]
            brute = [sum(l < ll and rr < r for ll, rr in segments) for l, r in segments]
            ranks = {r: i + 1 for i, r in enumerate(sorted(r for l, r in segments))}
            bit, treap = Fenwick(n), RankedTreap()
            swept, ranked, merged = [0] * n, [0] * n, [0] * n
            for i in sorted(range(n), key=lambda i: segments[i][0], reverse=True):
                r = segments[i][1]
                swept[i] = bit.prefix(ranks[r] - 1)
                ranked[i] = treap.rank(r)
                bit.add(ranks[r])
                treap.add(r)

            def merge_count(items):
                if len(items) <= 1:
                    return items
                mid = len(items) // 2
                left, right = merge_count(items[:mid]), merge_count(items[mid:])
                out, j = [], 0
                for value, idx in left:
                    while j < len(right) and right[j][0] < value:
                        out.append(right[j])
                        j += 1
                    merged[idx] += j
                    out.append((value, idx))
                return out + right[j:]

            merge_count([(segments[i][1], i) for i in
                         sorted(range(n), key=lambda i: segments[i][0])])
            for actual in (swept, ranked, merged):
                self.assertEqual(actual, brute, segments)

    def test_961E_sweep_threshold_against_all_pairs(self):
        rng = random.Random(961)
        for _ in range(400):
            n = rng.randint(1, 35)
            a = [0] + [rng.randint(1, 70) for _ in range(n)]
            ordered = sorted(range(1, n + 1), key=lambda i: a[i], reverse=True)
            bit = Fenwick(n)
            ans = cursor = 0
            for x in range(n, 0, -1):
                while cursor < n and a[ordered[cursor]] >= x:
                    bit.add(ordered[cursor])
                    cursor += 1
                upper = min(n, a[x])
                if upper > x:
                    ans += bit.prefix(upper) - bit.prefix(x)
            brute = sum(y <= a[x] and x <= a[y]
                        for x in range(1, n + 1) for y in range(x + 1, n + 1))
            self.assertEqual(ans, brute, a)

    def test_911A_greedy_nearest_minimum_against_all_pairs(self):
        for n in range(2, 8):
            for a in itertools.product(range(3), repeat=n):
                low = min(a)
                indices = [i for i, v in enumerate(a) if v == low]
                if len(indices) < 2:
                    continue
                brute = min(j - i for i, j in itertools.combinations(indices, 2))
                ans, last = n, None
                for i, value in enumerate(a):
                    if value == low:
                        if last is not None:
                            ans = min(ans, i - last)
                        last = i
                self.assertEqual(ans, brute, a)


if __name__ == '__main__':
    unittest.main()
