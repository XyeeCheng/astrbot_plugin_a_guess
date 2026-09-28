"""Small independent oracles for the ten composite cards; no network required."""
import itertools as it
import math
import random
import unittest
from collections import Counter, deque
from fractions import Fraction


class AlgorithmChecks(unittest.TestCase):
    def setUp(self): self.r = random.Random(20260928)

    def test_665E_prefix_binary_trie(self):
        for _ in range(150):
            a=[self.r.randrange(16) for _ in range(self.r.randint(1,9))]
            k=self.r.randint(1,20)
            trie={}
            def insert(x):
                node=trie
                for b in range(4,-1,-1):
                    node=node.setdefault((x>>b)&1,{'count':0})
                    node['count']+=1
            def less(x):
                node=trie
                ans=0
                for b in range(4,-1,-1):
                    bit=(x>>b)&1
                    if (k>>b)&1:
                        ans+=node.get(bit,{}).get('count',0)
                        node=node.get(bit^1,{})
                    else: node=node.get(bit,{})
                return ans
            insert(0)
            p=ans=0
            for i,x in enumerate(a):
                p^=x
                ans+=i+1-less(p)
                insert(p)
            brute=0
            for l in range(len(a)):
                x=0
                for r in range(l,len(a)):
                    x^=a[r]
                    brute+=x>=k
            self.assertEqual(ans,brute)

    def test_808G_automaton_dp(self):
        for _ in range(100):
            s=''.join(self.r.choice('ab?') for _ in range(self.r.randint(1,7)))
            t=''.join(self.r.choice('ab') for _ in range(self.r.randint(1,3)))
            m=len(t)
            pi=[0]*m
            for i in range(1,m):
                j=pi[i-1]
                while j and t[i]!=t[j]: j=pi[j-1]
                if t[i]==t[j]: j+=1
                pi[i]=j
            dp={0:0}
            for ch in s:
                nd={}
                for j,v in dp.items():
                    for c in ('ab' if ch=='?' else ch):
                        q=j
                        while q and t[q]!=c: q=pi[q-1]
                        if t[q]==c: q+=1
                        hit=q==m
                        if hit: q=pi[-1]
                        nd[q]=max(nd.get(q,-1),v+hit)
                dp=nd
            brute=0
            for replacement in it.product('ab',repeat=s.count('?')):
                chars=iter(replacement)
                text=''.join(next(chars) if c=='?' else c for c in s)
                brute=max(brute,sum(text[i:i+m]==t for i in range(len(s)-m+1)))
            self.assertEqual(max(dp.values()),brute)

    def test_846D_binary_answer_prefix2d(self):
        for _ in range(100):
            n,m=self.r.randint(1,4),self.r.randint(1,4)
            k=self.r.randint(1,min(n,m))
            a=[[self.r.choice([0,1,3,8,999]) for _ in range(m)] for _ in range(n)]
            def check(t):
                p=[[0]*(m+1) for _ in range(n+1)]
                for i in range(n):
                    for j in range(m):
                        p[i+1][j+1]=p[i][j+1]+p[i+1][j]-p[i][j]+(a[i][j]<=t)
                return any(p[i+k][j+k]-p[i][j+k]-p[i+k][j]+p[i][j]==k*k
                           for i in range(n-k+1) for j in range(m-k+1))
            lo,hi=-1,9
            while hi-lo>1:
                mid=(lo+hi)//2
                if check(mid): hi=mid
                else: lo=mid
            ans=hi if hi<9 else -1
            brute=min(max(a[i+x][j+y] for x in range(k) for y in range(k))
                      for i in range(n-k+1) for j in range(m-k+1))
            self.assertEqual(ans,brute if brute!=999 else -1)

    def test_893E_factors_and_combinations(self):
        for x in range(1,13):
            for y in range(1,4):
                v=x
                ans=2**(y-1)
                p=2
                while p*p<=v:
                    e=0
                    while v%p==0: v//=p; e+=1
                    ans*=math.comb(e+y-1,e)
                    p+=1
                if v>1: ans*=y
                divisors=[d for d in range(-x,x+1) if d and x%d==0]
                brute=sum(math.prod(a)==x for a in it.product(divisors,repeat=y))
                self.assertEqual(ans,brute)

    def test_920F_skip_stable_and_fenwick(self):
        for _ in range(40):
            n=12
            a=[self.r.randint(1,100) for _ in range(n)]
            naive=a[:]
            bit=[0]*(n+1)
            live=set(range(n))
            def update(i,d):
                i+=1
                while i<=n: bit[i]+=d; i+=i&-i
            def prefix(i):
                ans=0
                while i: ans+=bit[i]; i-=i&-i
                return ans
            def divisors(x): return sum(x%d==0 for d in range(1,x+1))
            for i,x in enumerate(a): update(i,x)
            for __ in range(40):
                l=self.r.randrange(n); r=self.r.randrange(l,n)
                if self.r.randrange(2):
                    for i in list(live):
                        if l<=i<=r:
                            nxt=divisors(a[i]); update(i,nxt-a[i]); a[i]=nxt
                            if nxt<=2: live.remove(i)
                    naive[l:r+1]=map(divisors,naive[l:r+1])
                self.assertEqual(prefix(r+1)-prefix(l),sum(naive[l:r+1]))

    def test_920G_inclusion_binary(self):
        for _ in range(100):
            x,p,k=self.r.randint(1,30),self.r.randint(1,30),self.r.randint(1,20)
            factors=[d for d in range(2,p+1) if p%d==0 and all(d%q for q in range(2,d))]
            def count(v):
                ans=v
                for mask in range(1,1<<len(factors)):
                    selected=[factors[i] for i in range(len(factors)) if mask>>i&1]
                    ans+=(-1)**len(selected)*(v//math.prod(selected))
                return ans
            base=count(x); lo=x; hi=x+1
            while count(hi)-base<k: hi*=2
            while hi-lo>1:
                mid=(hi+lo)//2
                if count(mid)-base>=k: hi=mid
                else: lo=mid
            brute=x
            for __ in range(k):
                brute+=1
                while math.gcd(brute,p)!=1: brute+=1
            self.assertEqual(hi,brute)

    def test_1000E_bridges_and_tree_diameter(self):
        for _ in range(70):
            n=self.r.randint(2,7)
            edges=[(i,self.r.randrange(i)) for i in range(1,n)]
            edges += [(i,j) for i in range(n) for j in range(i) if (i,j) not in edges and self.r.randrange(4)==0]
            graph=[[] for _ in range(n)]
            for idx,(u,v) in enumerate(edges): graph[u].append((v,idx)); graph[v].append((u,idx))
            tin=[-1]*n; low=[0]*n; bridges=set(); timer=0
            def dfs(u,pe=-1):
                nonlocal timer
                tin[u]=low[u]=timer; timer+=1
                for v,e in graph[u]:
                    if e==pe: continue
                    if tin[v]<0:
                        dfs(v,e); low[u]=min(low[u],low[v])
                        if low[v]>tin[u]: bridges.add(e)
                    else: low[u]=min(low[u],tin[v])
            dfs(0)
            comp=[-1]*n
            for start in range(n):
                if comp[start]>=0: continue
                todo=[start]; comp[start]=start
                for u in todo:
                    for v,e in graph[u]:
                        if e not in bridges and comp[v]<0: comp[v]=start; todo.append(v)
            tree={c:[] for c in comp}
            for e in bridges:
                u,v=edges[e]; tree[comp[u]].append(comp[v]); tree[comp[v]].append(comp[u])
            def far(s):
                dist={s:0}; q=[s]
                for u in q:
                    for v in tree[u]:
                        if v not in dist: dist[v]=dist[u]+1; q.append(v)
                return max(dist,key=dist.get),max(dist.values())
            ans=far(far(comp[0])[0])[1]
            def reachable(s,t,skip):
                seen={s}; q=[s]
                for u in q:
                    for v,e in graph[u]:
                        if e!=skip and v not in seen: seen.add(v); q.append(v)
                return t in seen
            brute=max(sum(not reachable(s,t,e) for e in range(len(edges))) for s in range(n) for t in range(n))
            self.assertEqual(ans,brute)

    def test_1096F_expected_inversions(self):
        for _ in range(100):
            n=self.r.randint(1,6); a=list(range(1,n+1)); self.r.shuffle(a)
            a=[x if self.r.randrange(2) else -1 for x in a]
            missing=[x for x in range(1,n+1) if x not in a]; k=len(missing)
            bit=[0]*(n+1); known=0; ans=Fraction(k*(k-1),4); left=0
            for x in a:
                if x==-1: left+=1; continue
                cnt=0; i=x
                while i: cnt+=bit[i]; i-=i&-i
                ans+=known-cnt; known+=1; i=x
                while i<=n: bit[i]+=1; i+=i&-i
                if k:
                    ans+=Fraction(left*sum(y>x for y in missing)+(k-left)*sum(y<x for y in missing),k)
            values=[]
            for perm in it.permutations(missing):
                items=iter(perm); b=[next(items) if x==-1 else x for x in a]
                values.append(sum(b[i]>b[j] for i in range(n) for j in range(i+1,n)))
            self.assertEqual(ans,Fraction(sum(values),len(values)))

    def test_1207D_inclusion_permutations(self):
        for _ in range(70):
            n=self.r.randint(1,6)
            a=[(self.r.randint(1,3),self.r.randint(1,3)) for _ in range(n)]
            def factorial_groups(seq): return math.prod(math.factorial(x) for x in Counter(seq).values())
            ordered=sorted(a)
            both=factorial_groups(a) if all(ordered[i][1]<=ordered[i+1][1] for i in range(n-1)) else 0
            ans=math.factorial(n)-factorial_groups(x for x,y in a)-factorial_groups(y for x,y in a)+both
            brute=0
            for perm in it.permutations(range(n)):
                b=[a[i] for i in perm]
                brute+=not all(b[i][0]<=b[i+1][0] for i in range(n-1)) and not all(b[i][1]<=b[i+1][1] for i in range(n-1))
            self.assertEqual(ans,brute)

    def test_1354E_bipartite_knapsack(self):
        for _ in range(80):
            n=self.r.randint(1,6)
            edges=[(i,j) for i in range(n) for j in range(i) if self.r.randrange(3)==0]
            n1=self.r.randrange(n+1); n2=self.r.randrange(n-n1+1); n3=n-n1-n2
            graph=[[] for _ in range(n)]
            for u,v in edges: graph[u].append(v); graph[v].append(u)
            color=[-1]*n; possible={0}; ok=True
            for start in range(n):
                if color[start]>=0: continue
                q=[start]; color[start]=0; counts=[1,0]
                for u in q:
                    for v in graph[u]:
                        if color[v]<0: color[v]=color[u]^1; counts[color[v]]+=1; q.append(v)
                        elif color[v]==color[u]: ok=False
                possible={x+y for x in possible for y in counts if x+y<=n2}
            ans=ok and n2 in possible
            brute=any(c.count(1)==n1 and c.count(2)==n2 and c.count(3)==n3 and
                      all(abs(c[u]-c[v])==1 for u,v in edges) for c in it.product((1,2,3),repeat=n))
            self.assertEqual(ans,brute)


if __name__=='__main__': unittest.main()
