import os, collections, statistics as st, sys, math, cmath
P2="/root/autodl-tmp/PBR"; sys.path.insert(0,"/root/autodl-tmp/PBR_vt_20261031")
from pbrcost import CFG, ORDER, phase_scan_anchor, _rows, _per_step_N
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

print("%-5s %6s | 周期 p 的方差占比 (R^2)  各 p 独立拟合"%("case","n"))
print("%-5s %6s | %s"%("",""," ".join("p=%d"%p for p in (4,5,6,7,8,9))))
for tag in ORDER:
    tab=build(tag)
    ts=sorted({t for t,a in tab})
    as_=[a for a in range(1,7)]
    row=[]
    for p in (4,5,6,7,8,9):
        r2s=[]
        for a in as_:
            y=[(t,tab[(t,a)]) for t in ts if (t,a) in tab]
            if len(y)<3*p: continue
            n=len(y)
            # 最小二乘拟合 p 个相位基（常数 + sin/cos），用残差平方和
            def design(pk):
                M=[]
                for t,_v in y:
                    M.append([1.0]+[f(2*math.pi*k*t/pk) for k in range(1,(pk//2)+1) for f in (math.sin,math.cos)])
                return M
            M=design(p)
            ncol=len(M[0]); 
            # 正规方程
            import numpy as np
            Am=np.array(M); b=np.array([v for _,v in y])
            try:
                coef,*_=np.linalg.lstsq(Am,b,rcond=None)
            except Exception: continue
            pred=Am@coef; ss_res=float(((b-pred)**2).sum()); ss_tot=float(((b-b.mean())**2).sum())
            if ss_tot>0: r2s.append(1-ss_res/ss_tot)
        row.append(st.mean(r2s) if r2s else float('nan'))
    print("%-5s %6d | %s"%(tag,len(ts)," ".join("%.3f"%v for v in row)))
