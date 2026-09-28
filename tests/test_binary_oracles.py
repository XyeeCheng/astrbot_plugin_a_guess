"""Exhaustive short-string checks of the two newly accepted normal binary cores."""
import itertools
import unittest


def first_true(n, check):
    lo, hi = 1, n
    while lo < hi:
        mid = (lo + hi) // 2
        if check(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo if check(lo) else 0


class BinaryCoreOracles(unittest.TestCase):
    def test_1354b_binary_length_and_prefix_counts(self):
        for n in range(1, 8):
            for chars in itertools.product('123', repeat=n):
                s = ''.join(chars)
                prefix = [[0, 0, 0]]
                for ch in s:
                    row = prefix[-1].copy()
                    row[int(ch) - 1] += 1
                    prefix.append(row)
                def check(k):
                    return any(all(prefix[r][j] > prefix[r-k][j] for j in range(3)) for r in range(k, n+1))
                brute = min((r-l for l in range(n) for r in range(l+1, n+1)
                             if len(set(s[l:r])) == 3), default=0)
                self.assertEqual(first_true(n, check), brute, s)

    def test_888c_binary_length_and_all_windows(self):
        for n in range(1, 8):
            for chars in itertools.product('abc', repeat=n):
                s = ''.join(chars)
                def check(k):
                    common = set('abc')
                    counts = {c: s[:k].count(c) for c in 'abc'}
                    for r in range(k, n+1):
                        common.intersection_update(c for c, count in counts.items() if count)
                        if r < n:
                            counts[s[r-k]] -= 1
                            counts[s[r]] += 1
                    return bool(common)
                # Independent direct geometry: maximum gap between consecutive
                # occurrences, including the virtual boundaries 0 and n+1.
                costs = []
                for ch in set(s):
                    positions = [0] + [i+1 for i, c in enumerate(s) if c == ch] + [n+1]
                    costs.append(max(b-a for a, b in zip(positions, positions[1:])))
                self.assertEqual(first_true(n, check), min(costs), s)


if __name__ == '__main__':
    unittest.main()
