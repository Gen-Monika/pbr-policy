#!/usr/bin/env python3
"""诊断：s=1 的年龄曲线是否真的平坦？检查 K=3/K=5 下实际年龄分布与迭代数。"""
import os, re, statistics as st
from collections import defaultdict
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")

def per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out

def load_csv(p):
    rows=[]
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

print("=" * 100)
print("诊断：s=1 各 K 下的真实年龄分布与对应迭代数")
print("=" * 100)
for S in (1,):
    for K in (1, 2, 3, 5, 8):
        f = "s_pc_s%d_k%d_r1.csv" % (S, K)
        lg = "srun/log.s%dr1k%d" % (S, K)
        rows = load_csv(f)
        if not rows or not os.path.exists(lg): 
            print("  s=%d K=%d 缺文件" % (S,K)); continue
        Ns = per_step_N(lg)
        n = min(len(Ns), len(rows))
        rows, Ns = rows[:n], Ns[:n]
        ages = defaultdict(list)
        for d, it in zip(rows, Ns):
            rf = int(d["reusedFrom"]); ti = int(d["timeIndex"])
            a = 0 if rf < 0 else (ti - rf)
            ages[a].append(it)
        tot = sum(len(v) for v in ages.values())
        print("\n  ── s=%d K=%d  步数=%d ──" % (S, K, tot))
        print("    年龄: " + "  ".join("%d" % a for a in sorted(ages)))
        print("    样本: " + "  ".join("%d" % len(ages[a]) for a in sorted(ages)))
        print("    N中位: " + "  ".join("%.0f" % st.median(ages[a]) for a in sorted(ages)))
