#!/usr/bin/env python3
"""★ 校验：report 的隔离 tIter 与在环 tApplyAccum 是否同一口径。"""
import os, statistics as st
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
def load(p, only_rep=False):
    rows=[]
    if not os.path.exists(p): return rows
    for ln in open(p):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(CSV_HDR,q))
            for k in d:
                if k not in ("field","kind"): d[k]=float(d[k])
            if only_rep and int(d["rep"])<0: continue
            rows.append(d)
        except ValueError: pass
    return rows

print("=" * 104)
print("★ 在环 apply（tApplyAccum/nApplyCalls）与隔离 tIter 的口径对比（s=3, 第1轮）")
print("=" * 104)
print("  %4s %14s %14s %14s %12s" %
      ("K","在环apply/µs","隔离 tIter/µs","隔离 ma/µs","比值"))
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    n = rows[-1]["nApplyCalls"]
    ap = rows[-1]["tApplyAccum"]/n*1e6 if n else float("nan")
    rep = load("s_pc_s3_k%d_r1.csv" % K, only_rep=True)
    ti = st.median([d["tIter"] for d in rep])*1e6
    ma = st.median([d["ma"] for d in rep])*1e6
    print("  %4d %14.2f %14.2f %14.2f %12.2f" % (K, ap, ti, ma, ap/ti))

print()
print("  ── 分解成本口径：ΣtPCSetup 与 nBuildPC ──")
print("  %4s %8s %14s %14s %12s" % ("K","nBuildPC","ΣtPCSetup/s","tSetupAll/s","单次/µs"))
for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    nb = rows[-1]["nBuildPC"]
    su = sum(d["tPCSetup"] for d in rows)
    ta = rows[-1]["tSetupAll"]
    print("  %4d %8d %14.3f %14.3f %12.0f" % (K, nb, su, ta, su/nb*1e6))

print()
print("  ── ★ 用【同口径】重算成本模型 ──")
print("     做法：tPCSetup 与 tIter 都取每个 K 自己的重建步中位（自洽口径）")
import re
TIME_RE=re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE=re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
def per_step_N(p):
    out,cur=[],[]
    for ln in open(p,errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur))
            cur=[]; continue
        m=SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out

for K in (1,2,3,4,5,6,8,10):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    rep = load("s_pc_s3_k%d_r1.csv" % K, only_rep=True)
    Ns = per_step_N("srun/log.s3r1k%d" % K)
    if not rows or not Ns: continue
    n=min(len(rows),len(Ns)); Ns=Ns[:n]
    nb = int(rows[-1]["nBuildPC"])
    su = sum(d["tPCSetup"] for d in rows)
    ti = st.median([d["tIter"] for d in rep if d["reused"]==0])
    iters = sum(Ns)
    model = su + iters*ti
    print("     K=%2d  重建%4d  ΣtPCS=%.3fs  迭代数=%6d  tIter=%.1fµs  ⇒ 模型=%.3fs"
          % (K, nb, su, iters, ti*1e6, model))
