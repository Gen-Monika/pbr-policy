#!/usr/bin/env python3
"""复用步 vs 重建步的 tIter/ma/mp：反序列化是否污染后续计时。"""
import os, statistics as st
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
def load(p):
    rows=[]
    if not os.path.exists(p): return rows
    for ln in open(p):
        q=ln.rstrip("\n").split(",")
        if len(q)!=25: continue
        try:
            d=dict(zip(CSV_HDR,q))
            for k in d:
                if k not in ("field","kind"): d[k]=float(d[k])
            if int(d["rep"]) < 0: continue
            rows.append(d)
        except ValueError: pass
    return rows

print("=" * 104)
print("★ 重建步 vs 复用步：tIter / ma / mp / tFreeze（s=3, 第 1 轮）")
print("=" * 104)
for K in (1,2,3,5,8):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    if not rows: continue
    reb = [d for d in rows if d["reused"]==0]
    reu = [d for d in rows if d["reused"]!=0]
    med = lambda L,k: (st.median([d[k] for d in L])*1e6 if L else float("nan"))
    print("\n  ── K=%d  (重建 %d 行 / 复用 %d 行) ──" % (K, len(reb), len(reu)))
    print("     %-8s %10s %10s %10s %10s" % ("", "tIter/µs", "ma/µs", "mp/µs", "tFreeze/µs"))
    print("     %-8s %10.2f %10.2f %10.2f %10.2f"
          % ("重建步", med(reb,"tIter"), med(reb,"ma"), med(reb,"mp"), med(reb,"tFreeze")))
    print("     %-8s %10.2f %10.2f %10.2f %10.2f"
          % ("复用步", med(reu,"tIter"), med(reu,"ma"), med(reu,"mp"), med(reu,"tFreeze")))

print()
print()
print("  (below: tIter split by N)")
print("  ── tIter 与 N 的联合分布（同一 N 下比较重建/复用步）──")
import re
TIME_RE=re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE=re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
def per_step_N(p):
    out,cur=[],[]
    for ln in open(p,errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(cur)
            cur=[]; continue
        m=SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(cur)
    return out

for K in (1,3,8):
    rows = load("s_pc_s3_k%d_r1.csv" % K)
    Ns = per_step_N("srun/log.s3r1k%d" % K)
    if not rows or not Ns: continue
    n=min(len(rows),len(Ns)); rows,Ns=rows[:n],Ns[:n]
    byN = {}
    for d,N in zip(rows,Ns):
        tot=sum(N)
        byN.setdefault(tot, {"reb":[], "reu":[]})["reb" if d["reused"]==0 else "reu"].append(d["tIter"]*1e6)
    print("\n     K=%d" % K)
    print("     %6s %22s %22s" % ("N_step", "重建步 tIter 中位(n)", "复用步 tIter 中位(n)"))
    for N in sorted(byN):
        if N>35: continue
        rb, ru = byN[N]["reb"], byN[N]["reu"]
        f=lambda v: ("%8.2f (%3d)" % (st.median(v), len(v))) if v else "%13s" % "-"
        print("     %6d %22s %22s" % (N, f(rb), f(ru)))
