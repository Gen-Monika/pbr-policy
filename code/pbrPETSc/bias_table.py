#!/usr/bin/env python3
"""
★★★ 统一口径的判据偏差表

ΔN_step(K) := (ΣN(K) − ΣN(1)) / 步数
  —— 按各 K 的【真实访龄分布】加权，与实测一致。
（不用"按年龄分组取均值"：会被尾部离群点污染。）

判据：ΔN_step(K) < r/s ⇒ 该 K 可复用。
预测最优 K = 首次失效的 K − 1。
"""
import os, re, statistics as st
from collections import defaultdict

WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def per_step_N(path):
    out, cur = [], []
    if not os.path.exists(path):
        return out
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def med_r(tag, Ks, rounds):
    rs = []
    for K in Ks:
        for R in rounds:
            p = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            if not os.path.exists(p): continue
            for ln in open(p):
                q = ln.rstrip("\n").split(",")
                if len(q) != 25: continue
                try:
                    d = dict(zip(CSV_HDR, q))
                    if float(d["rep"]) < 0: continue
                    if float(d["reused"]) == 0 and float(d["tPCSetup"]) > 1e-4 and float(d["tIter"]) > 0:
                        rs.append(float(d["r"]))
                except ValueError: pass
    return st.median(rs) if rs else float("nan")


def case(name, tag, outfile, logdir, rounds, Ks):
    W = defaultdict(dict)
    if not os.path.exists(outfile):
        print("  (缺 %s)" % outfile); return None
    for ln in open(outfile):
        m = WL.search(ln)
        if m: W[int(m.group(1))][int(m.group(2))] = float(m.group(4))
    r_ = med_r(tag, Ks, rounds)
    N = {}
    for K in Ks:
        ns = []
        for R in rounds:
            v = per_step_N(os.path.join(logdir, "log.r%dk%d" % (R, K)))
            if v: ns.append(sum(v))
        if ns: N[K] = st.median(ns)
    if 1 not in N: return None
    nst = len(per_step_N(os.path.join(logdir, "log.r%dk1" % rounds[0])))
    thr = r_ / 3.0
    print("\n  ── %s   r=%.2f  阈值 r/s=%.2f  步数=%d ──" % (name, r_, thr, nst))
    print("  %4s %12s %14s %10s %10s" %
          ("K", "Σ迭代数", "ΔN_step", "判定", "墙钟/s"))
    firstbad = None
    wall = {}
    for K in Ks:
        if K not in N: continue
        dn = (N[K] - N[1]) / max(nst, 1)
        bad = dn >= thr
        if bad and firstbad is None: firstbad = K
        wall[K] = st.median([W[R][K] for R in rounds if K in W.get(R, {})])
        print("  %4d %12d %14.1f %10s %10.2f"
              % (K, N[K], dn, "重建 ✗" if bad else "复用 ✓", wall[K]))
    pred = (firstbad - 1) if firstbad else max(Ks)
    best = min(wall, key=lambda k: wall[k])
    print("  ⇒ 判据预测最优 K = %d ；实测最优 K = %d ；偏差 = %+d"
          % (pred, best, best - pred))
    return dict(name=name, r=r_, thr=thr, pred=pred, best=best,
                bias=best - pred, nst=nst)


print("=" * 100)
print("★★★ 判据偏差表（统一口径 ΔN_step = 累计差/步数）")
print("=" * 100)
rows = []
rows.append(case("base 2268 @ L10", "fx",  "fx.out",  "fixed", [1,2,3,4,5], [1,2,3,5,8]))
rows.append(case("base 2268 @ L15", "l15", "l15.out", "l15",   [1,2,3,4,5], [1,2,3,5,8]))
rows.append(case("base 2268 @ L20", "l20", "l20.out", "l20",   [1,2,3,4,5], [1,2,3,5,8]))
rows.append(case("fine 9072 @ L10", "fl10","fl10_scan.out","fl10run",[1,2],[1,3,5]))
rows.append(case("fine 9072 @ L20", "fine","fine_scan.out","finerun",[1,2,3],[1,2,3,5,8]))
rows.append(case("3x 20412 @ L20",  "x3",  "x3_scan.out","x3run",[1,2],[1,2,3,5,8]))

print("\n" + "=" * 100)
print("  ★★★ 汇总")
print("=" * 100)
print("  %-18s %10s %10s %10s %8s %8s" %
      ("配置", "r", "阈值r/s", "判据预测", "实测最优", "偏差"))
for r in rows:
    if r:
        print("  %-18s %10.2f %10.2f %10d %8d %+8d"
              % (r["name"], r["r"], r["thr"], r["pred"], r["best"], r["bias"]))
ok = [r["bias"] for r in rows if r]
if ok:
    print("\n  ⇒ 偏差集合 = %s" % ok)
    print("  ⇒ |偏差| = %s" % sorted(set(abs(b) for b in ok)))
    print("  ⇒ 方向一致性: %s" % ("全部同号" if len(set(b > 0 for b in ok)) == 1
                                  else "有正有负"))
