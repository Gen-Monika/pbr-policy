import os, collections, statistics as st, sys, json, random
P2="/root/autodl-tmp/PBR"; sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import CFG, ORDER, phase_scan_anchor, _rows, _per_step_N
A,K=6,7
random.seed(1)
def frames(tag):
    lvl,T,B0=CFG[tag]; Bscan=phase_scan_anchor(tag)
    cells=collections.defaultdict(list)
    for B in range(Bscan-A,Bscan+1):
        c=os.path.join(P2,"phs_%s_B%d_K%d_r1.csv"%(tag,B,K))
        l=os.path.join(P2,"phs_%s"%tag,"log.B%dK%d_r1"%(B,K))
        if not (os.path.exists(c) and os.path.exists(l)): continue
        rr=_rows(c); seen={}
        for x in rr:
            if int(x["rep"])>=0 and int(x["timeIndex"]) not in seen: seen[int(x["timeIndex"])]=x
        steps=[seen[t] for t in sorted(seen)]; Ns=_per_step_N(l); n=min(len(steps),len(Ns))
        for i in range(n):
            t=i+1; rf=int(steps[i]["reusedFrom"])
            cells[(t,0 if rf<0 else t-rf)].append(Ns[i])
    tab={k:st.median(v) for k,v in cells.items()}
    ts=sorted({t for t,a in tab}); as_=sorted({a for t,a in tab})
    fr={}
    for t in ts:
        p={a:tab[(t,a)] for a in as_ if (t,a) in tab}
        if 0 in p and len(p)>=4: fr[t]={a:p[a]-p[0] for a in p if a>0}
    return fr

def vs_removed(fr, key):
    g=collections.defaultdict(list)
    for t,v in fr.items(): g[key(t)].append(v)
    means={}
    for r,vs in g.items():
        common=set(vs[0])
        for v in vs[1:]: common&=set(v)
        common=sorted(common)
        if common: means[r]={a:st.mean(v[a] for v in vs) for a in common}
    ts=sorted(fr); raw=[];res=[]
    for t0,t1 in zip(ts,ts[1:]):
        g0,g1=fr[t0],fr[t1]; c=sorted(set(g0)&set(g1))
        if not c: continue
        raw.append(max(abs(g1[a]-g0[a]) for a in c))
        r0,r1=key(t0),key(t1)
        if r0 in means and r1 in means:
            c2=[a for a in c if a in means[r0] and a in means[r1]]
            if c2: res.append(max(abs((g1[a]-means[r1][a])-(g0[a]-means[r0][a])) for a in c2))
    if not raw or not res: return None
    return st.mean(raw), st.mean(res), 1-st.mean(res)/st.mean(raw)

for tag in ORDER:
    fr=frames(tag)
    if len(fr)<20: continue
    real=vs_removed(fr, lambda t: t%7)
    ts=sorted(fr)
    nulls=[]
    for _ in range(40):
        lab={t:random.randrange(7) for t in ts}
        r=vs_removed(fr, lambda t: lab[t])
        if r: nulls.append(r[2])
    print("%-5s  t_mod7: raw=%.2f res=%.2f removed=%.0f pct  | random-group control: median=%.0f pct 95pct=%.0f pct" % (
        tag, real[0], real[1], 100 * real[2],
        100 * sorted(nulls)[len(nulls) // 2], 100 * sorted(nulls)[int(.95 * len(nulls))]))
