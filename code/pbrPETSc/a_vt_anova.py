import os, collections, statistics as st, sys
P2="/root/autodl-tmp/PBR"; sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import CFG, ORDER, phase_scan_anchor, _rows, _per_step_N
import numpy as np
A,K=6,7
def build(tag):
    lvl,T,B0=CFG[tag]; Bs=phase_scan_anchor(tag)
    cells=collections.defaultdict(list)
    for B in range(Bs-A,Bs+1):
        c=os.path.join(P2,"phs_%s_B%d_K%d_r1.csv"%(tag,B,K)); l=os.path.join(P2,"phs_%s"%tag,"log.B%dK%d_r1"%(B,K))
        if not (os.path.exists(c) and os.path.exists(l)): continue
        rr=_rows(c); seen={}
        for x in rr:
            if int(x["rep"])>=0 and int(x["timeIndex"]) not in seen: seen[int(x["timeIndex"])]=x
        steps=[seen[t] for t in sorted(seen)]; Ns=_per_step_N(l); n=min(len(steps),len(Ns))
        for i in range(n):
            t=i+1; rf=int(steps[i]["reusedFrom"]); cells[(t,0 if rf<0 else t-rf)].append(Ns[i])
    return {k:st.median(v) for k,v in cells.items()}

print("单因素方差分析：固定 age，按来源锚点 B≡t-a (mod 7) 分组，N(t,a) 是否有系统性差异")
print("%-5s %-4s %8s %8s %8s %8s"%("case","age","组间F","临界F(.05)","组间sd","p≈"))
for tag in ORDER:
    tab=build(tag)
    ts=sorted({t for t,a in tab})
    for a in (1,2,3,4):
        groups=collections.defaultdict(list)
        for t in ts:
            if (t,a) in tab: groups[(t-a)%7].append(tab[(t,a)])
        gs=[np.array(v) for v in groups.values() if len(v)>=3]
        if len(gs)<3: continue
        # 手工 one-way ANOVA
        allv=np.concatenate(gs); k=len(gs); N=len(allv)
        grand=allv.mean()
        ssb=sum(len(g)*(g.mean()-grand)**2 for g in gs)
        ssw=sum(((g-g.mean())**2).sum() for g in gs)
        dfb=k-1; dfw=N-k
        if dfw<=0 or ssw<=0: continue
        F=(ssb/dfb)/(ssw/dfw)
        try:
            from scipy import stats as ss
            p=1-ss.f.cdf(F,dfb,dfw)
            ps="%.3f"%p
        except Exception:
            ps="-"
        # 组间 sd（各组均值自身的标准差）
        gm=[g.mean() for g in gs]
        print("%-5s %-4d %8.2f %8.2f %8.2f %8s"%(tag,a,F,2.10,float(np.std(gm,ddof=1)),ps))
