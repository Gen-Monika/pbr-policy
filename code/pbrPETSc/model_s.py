#!/usr/bin/env python3
"""成本模型逐项核算：找出模型与实测背离的项。"""
import os, re, statistics as st
from collections import defaultdict
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

def load_csv(p):
    rows=[]
    if not os.path.exists(p): return rows
    for ln in open(p):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(CSV_HDR,q))
            for k in d:
                if k not in ("field","kind"): d[k]=float(d[k])
            rows.append(d)
        except ValueError: pass
    return rows

# 老化曲线（来自 diag_s.py，s=1 实测）
AGE = {1: {0:9,1:17,2:27,3:38,4:52,5:68,6:92,7:123},
       2: {}, 3: {}}
# 从 K=8 的 run 取 s=2/3 的曲线
for S,K in ((2,8),(3,8)):
    f="s_pc_s%d_k%d_r1.csv"%(S,K); lg="srun/log.s%dr1k%d"%(S,K)
    SOLVE_RE=re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
    TIME_RE=re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
    def ps(p):
        out,cur=[],[]
        for ln in open(p,errors="ignore"):
            if TIME_RE.match(ln):
                if cur: out.append(sum(cur))
                cur=[]; continue
            m=SOLVE_RE.search(ln)
            if m: cur.append(int(m.group(1)))
        if cur: out.append(sum(cur))
        return out
    rows=load_csv(f)
    if not rows: continue
    Ns=ps(lg); n=min(len(Ns),len(rows)); rows,Ns=rows[:n],Ns[:n]
    ag=defaultdict(list)
    for d,it in zip(rows,Ns):
        rf=int(d["reusedFrom"]); ti=int(d["timeIndex"])
        ag[0 if rf<0 else ti-rf].append(it)
    AGE[S]={a:st.median(v) for a,v in ag.items()}

print("=" * 104)
print("成本模型逐项核算（levels=10）")
print("=" * 104)
print("\n  老化曲线 N_step(a)：")
print("  %4s " % "s" + "".join("%8s" % ("a=%d"%a) for a in range(8)))
for S in (1,2,3):
    print("  %4d " % S + "".join("%8.0f" % AGE[S].get(a,float("nan")) for a in range(8)))

# 取各 s 在 K=1 时的实测开销项
res={}
for S in (1,2,3):
    print("\n" + "─"*104)
    print("  ── s=%d ──" % S)
    rows1 = load_csv("s_pc_s%d_k1_r1.csv" % S)
    if not rows1: 
        print("     缺 s_pc_s%d_k1_r1.csv" % S); continue
    nstep = len(rows1)
    tsetup = st.median([d["tPCSetup"] for d in rows1 if d["tPCSetup"]>1e-4])
    tit = st.median([d["tIter"] for d in rows1 if d["tIter"]>0])
    tfreeze = st.median([d["tFreeze"] for d in rows1])
    tasm = st.median([d["tAssemble"] for d in rows1])
    tconv = st.median([d["tConvert"] for d in rows1])
    print("     单次: tPCSetup=%.1fus tIter=%.1fus tFreeze=%.1fus tAssemble=%.1fus tConvert=%.1fus"
          % (tsetup*1e6, tit*1e6, tfreeze*1e6, tasm*1e6, tconv*1e6))
    print("     步数=%d" % nstep)
    print("\n     %5s %8s %10s %12s %12s %12s %12s" %
          ("K","重建数","快照数","分解/s","快照/s","迭代/s","模型总/s"))
    for K in (1,2,3,4,5,6,8,10):
        nb = sum(1 for i in range(nstep) if i % K == 0)
        nsnap = nb
        iters = sum(AGE[S].get(i % K, 0) for i in range(nstep))
        csetup = nb * tsetup
        cfreeze = nsnap * tfreeze
        cit = iters * tit
        tot = csetup + cfreeze + cit
        res.setdefault(S, {})[K] = dict(tot=tot, csetup=csetup, cfreeze=cfreeze,
                                        cit=cit, nb=nb, iters=iters)
        print("     %5d %8d %10d %12.3f %12.3f %12.3f %12.3f"
              % (K, nb, nsnap, csetup, cfreeze, cit, tot))
    best = min(res[S], key=lambda k: res[S][k]["tot"])
    print("     ⇒ 模型最优 K = %d" % best)
