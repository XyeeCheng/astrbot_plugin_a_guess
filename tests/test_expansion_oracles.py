"""Small independent comparisons for error-prone new card explanations.

These validate the named ideas on small inputs, not Codeforces submissions.
"""
import functools
import heapq
import itertools as it
import math
import random
import unittest
from fractions import Fraction


class ExpansionOracles(unittest.TestCase):
    def setUp(self): self.rng=random.Random(20260928)

    def test_702D_drive_breakpoints(self):
        for d in range(1,30):
            for k in range(1,8):
                for a,b,t in ((1,2,1),(1,2,10),(2,7,6)):
                    def cost(s):
                        return s*a+max(0,(s-1)//k)*t+(d-s)*b
                    best=min(cost(s) for s in range(d+1))
                    candidates={min(d,k),d,d//k*k}
                    self.assertEqual(min(cost(s) for s in candidates),best)

    def test_710E_length_dp_against_shortest_paths(self):
        for n in range(1,20):
            for x,y in ((1,1),(4,1),(1,7)):
                f=[0,x]+[0]*(n-1)
                for i in range(2,n+1):
                    f[i]=min(f[i-1]+x,f[i//2]+y if i%2==0 else f[(i+1)//2]+y+x)
                dist=[10**9]*(2*n+3);dist[0]=0;q=[(0,0)]
                while q:
                    d,p=heapq.heappop(q)
                    if d!=dist[p]: continue
                    for j,w in ((p-1,x),(p+1,x),(p*2,y)):
                        if 0<=j<len(dist) and d+w<dist[j]:
                            dist[j]=d+w;heapq.heappush(q,(d+w,j))
                self.assertEqual(f[n],dist[n])

    def test_803A_symmetric_matrix_lexicographic(self):
        for n in range(1,5):
            cells=[(i,j) for i in range(n) for j in range(i,n)]
            best={}
            for bits in it.product((0,1),repeat=len(cells)):
                a=[[0]*n for _ in range(n)]
                for (i,j),b in zip(cells,bits): a[i][j]=a[j][i]=b
                flat=tuple(it.chain.from_iterable(a));k=sum(flat)
                best[k]=max(best.get(k,()),flat)
            for k,want in best.items():
                a=[[0]*n for _ in range(n)];remaining=k
                for i,j in cells:
                    cost=1 if i==j else 2
                    if remaining>=cost: a[i][j]=a[j][i]=1;remaining-=cost
                self.assertEqual(tuple(it.chain.from_iterable(a)),want)

    def test_825E_labels_are_not_topological_order(self):
        for _ in range(50):
            n=5;order=self.rng.sample(range(n),n)
            edges=[(order[i],order[j]) for i in range(n) for j in range(i+1,n) if self.rng.randrange(3)==0]
            want=min(p for p in it.permutations(range(1,n+1)) if all(p[u]<p[v] for u,v in edges))
            out=[0]*n;pred=[[] for _ in range(n)]
            for u,v in edges: out[u]+=1;pred[v].append(u)
            heap=[-i for i in range(n) if not out[i]];heapq.heapify(heap);ans=[0]*n
            for label in range(n,0,-1):
                v=-heapq.heappop(heap);ans[v]=label
                for u in pred[v]:
                    out[u]-=1
                    if out[u]==0: heapq.heappush(heap,-u)
            self.assertEqual(tuple(ans),want)

    def test_846B_full_tasks_then_cheapest_parts(self):
        for _ in range(70):
            n,k=2,3;t=[self.rng.randint(1,4) for _ in range(k)];budget=self.rng.randrange(20)
            best=0
            for mask in range(1<<(n*k)):
                cost=sum(t[j%k] for j in range(n*k) if mask>>j&1)
                if cost>budget: continue
                score=mask.bit_count()+sum(all(mask>>(i*k+j)&1 for j in range(k)) for i in range(n))
                best=max(best,score)
            candidate=0
            for complete in range(n+1):
                left=budget-complete*sum(t)
                if left<0: continue
                score=complete*(k+1)
                for time in sorted(t):
                    take=min(n-complete,left//time);left-=take*time;score+=take
                candidate=max(candidate,score)
            self.assertEqual(candidate,best)

    def test_846F_ordered_random_endpoints(self):
        for _ in range(100):
            a=[self.rng.randrange(4) for _ in range(self.rng.randint(1,9))];n=len(a)
            brute=sum(len(set(a[min(l,r):max(l,r)+1])) for l in range(n) for r in range(n))
            last={};s=0
            for i,x in enumerate(a,1): s+=(i-last.get(x,0))*(n-i+1);last[x]=i
            self.assertEqual(Fraction(2*s-n,n*n),Fraction(brute,n*n))

    def test_873D_actual_recursive_call_count(self):
        def calls(a):
            if a==sorted(a): return 1
            mid=len(a)//2
            return 1+calls(a[:mid])+calls(a[mid:])
        for n in range(1,22):
            for k in range(1,2*n,2):
                a=list(range(1,n+1));budget=k-1
                def build(l,r):
                    nonlocal budget
                    if budget<2 or r-l<2: return
                    mid=(l+r)//2;a[mid-1],a[mid]=a[mid],a[mid-1];budget-=2
                    build(l,mid);build(mid,r)
                build(0,n)
                self.assertEqual(budget,0)
                self.assertEqual(calls(a),k)

    def test_884D_ternary_huffman_against_all_merge_orders(self):
        @functools.lru_cache(None)
        def brute(a):
            if len(a)==1:return 0
            best=10**9
            for count in (2,3):
                for indices in it.combinations(range(len(a)),count):
                    total=sum(a[i] for i in indices)
                    rest=tuple(sorted([a[i] for i in range(len(a)) if i not in indices]+[total]))
                    best=min(best,total+brute(rest))
            return best
        for _ in range(50):
            a=tuple(sorted(self.rng.randint(1,8) for _ in range(self.rng.randint(1,6))))
            heap=list(a);heapq.heapify(heap);ans=0
            if len(heap)%2==0:
                x=heapq.heappop(heap)+heapq.heappop(heap);ans+=x;heapq.heappush(heap,x)
            while len(heap)>1:
                x=sum(heapq.heappop(heap) for _ in range(3));ans+=x;heapq.heappush(heap,x)
            self.assertEqual(ans,brute(a))

    def test_893D_balance_interval_against_all_deposits(self):
        for _ in range(150):
            d=self.rng.randint(1,5);a=[self.rng.randint(-3,3) for _ in range(6)]
            states={0:0}
            for x in a:
                nxt={}
                for bal,cost in states.items():
                    for morning in range(bal,d+1):
                        after=morning+x
                        if after>d or (x==0 and after<0):continue
                        val=cost+(morning!=bal)
                        nxt[after]=min(nxt.get(after,99),val)
                states=nxt
            want=min(states.values(),default=-1)
            lo=hi=count=0
            for x in a:
                lo+=x;hi+=x
                if lo>d:count=-1;break
                hi=min(hi,d)
                if x==0:
                    if hi<0:count+=1;lo,hi=0,d
                    else:lo=max(lo,0)
            self.assertEqual(count,want,(d,a))

    def test_911C_residue_cover_classification(self):
        for periods in it.product(range(1,7),repeat=3):
            a,b,c=sorted(periods)
            predicted=(a==1 or a==b==2 or a==b==c==3 or (a,b,c)==(2,4,4))
            length=math.lcm(*periods)
            # Translate the first phase to zero; this preserves coverage.
            actual=any(all(t%a==0 or t%b==j or t%c==k for t in range(length)) for j in range(b) for k in range(c))
            self.assertEqual(predicted,actual,periods)

    def test_938C_difference_of_squares_reconstruction(self):
        for x in range(251):
            possible=any(n*n-(n//m)**2==x for n in range(1,max(2,(x+1)//2+1)) for m in range(1,n+1))
            found=x==0
            for u in range(1,math.isqrt(x)+1):
                if x%u:continue
                v=x//u
                if (u+v)%2:continue
                n,q=(u+v)//2,(v-u)//2
                if q and (m:=n//q)>=1 and n//m==q:found=True
            self.assertEqual(found,possible,x)

    def test_954G_greedy_placement_against_distributions(self):
        def distribute(k,n):
            if n==1:yield (k,);return
            for i in range(k+1):
                for rest in distribute(k-i,n-1):yield(i,)+rest
        for _ in range(100):
            n=self.rng.randint(1,5);r=self.rng.randrange(n+1);k=self.rng.randrange(5)
            a=[self.rng.randrange(4) for _ in range(n)]
            def strength(b):return min(sum(b[max(0,i-r):min(n,i+r+1)]) for i in range(n))
            want=max(strength([x+y for x,y in zip(a,extra)]) for extra in distribute(k,n))
            base=[sum(a[max(0,i-r):min(n,i+r+1)]) for i in range(n)]
            def feasible(target):
                diff=[0]*(n+1);active=used=0
                for i in range(n):
                    active+=diff[i];need=max(0,target-base[i]-active)
                    used+=need;active+=need
                    end=min(n,min(n-1,i+r)+r+1);diff[end]-=need
                return used<=k
            got=max(t for t in range(sum(a)+k+1) if feasible(t))
            self.assertEqual(got,want,(a,r,k))

    def test_985C_barrel_greedy_against_partitions(self):
        def partition(a,n,k):
            if n==0:yield ();return
            for chosen in it.combinations(range(1,len(a)),k-1):
                group={0,*chosen};rest=tuple(a[i] for i in range(len(a)) if i not in group)
                for mins in partition(rest,n-1,k):yield (a[0],)+mins
        for _ in range(90):
            n,k=self.rng.randint(1,3),self.rng.randint(1,3)
            a=tuple(sorted(self.rng.randint(1,8) for _ in range(n*k)));limit=self.rng.randrange(5)
            want=max((sum(p) for p in partition(a,n,k) if max(p)-min(p)<=limit),default=0)
            g=sum(v<=a[0]+limit for v in a);got=0
            if g>=n:
                pos=0
                for i in range(n):
                    got+=a[pos];pos+=1
                    pos+=min(k-1,g-pos-(n-i-1))
            self.assertEqual(got,want,(n,k,limit,a))


if __name__=='__main__':unittest.main()
