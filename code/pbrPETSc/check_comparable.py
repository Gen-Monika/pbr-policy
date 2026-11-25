#!/usr/bin/env python3
"""
★ 可比性核对：r 是相对量（tPCSetup/tIter），而 tIter 随 levels 变化。
必须同时看【绝对时间】，否则可能把"apply 变快"误读成"setup 变贵"。

同时核对：不同 levels 的【迭代数】差异极大（ILU(5) 是强预条件子），
因此"每步总代价"必须用各自实测的 N，不能跨 levels 借用。
"""
import os
import re
import statistics as st
from collections import defaultdict

H14 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,"
       "tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
H20 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
       "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")


def load14(path):
    out = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 14:
            continue
        try:
            d = dict(zip(H14, p))
            if float(d["tPCSetup"]) > 1e-4 and float(d["tIter"]) > 0:
                out.append({k: float(v) for k, v in d.items()
                            if k not in ("field", "kind")})
        except ValueError:
            continue
    return out


def load20(path):
    out = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 20:
            continue
        try:
            d = dict(zip(H20, p))
            if float(d["tPCSetup"]) > 1e-4 and float(d["tIter"]) > 0:
                out.append({k: float(v) for k, v in d.items()
                            if k not in ("field", "kind")})
        except ValueError:
            continue
    return out


def solves_for(logp):
    """每步的 3 次求解迭代数之和。"""
    steps, cur = [], []
    for ln in open(logp, errors="ignore"):
        if TIME_RE.match(ln):
            if cur:
                steps.append(sum(cur))
            cur = []
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur.append(int(ms.group(1)))
    if cur:
        steps.append(sum(cur))
    return steps


print("=" * 96)
print("★ 跨 levels 的绝对时间与迭代数对照")
print("=" * 96)

# L0 / L2 / L5（来自 bench_ilu_levels.csv，14 列，每级 344 行）
if os.path.exists("bench_ilu_levels.csv"):
    by = defaultdict(list)
    for ln in open("bench_ilu_levels.csv"):
        p = ln.rstrip("\n").split(",")
        if len(p) != 14:
            continue
        try:
            d = dict(zip(H14, p))
            lv = int(float(d["levels"]))
            if float(d["tPCSetup"]) > 1e-4 and float(d["tIter"]) > 0:
                by[lv].append({k: float(v) for k, v in d.items()
                               if k not in ("field", "kind")})
        except ValueError:
            continue

    print(f"\n  {'levels':>7} {'样本':>6} {'tPCSetup/µs':>12} {'tConvert/µs':>12} "
          f"{'ma(amul)/µs':>12} {'mp(apply)/µs':>13} {'tIter/µs':>9} {'r':>8}")
    for lv in sorted(by):
        v = by[lv]
        print(f"  {lv:>7} {len(v):>6} {st.median([d['tPCSetup'] for d in v])*1e6:>12.1f} "
              f"{st.median([d['tConvert'] for d in v])*1e6:>12.1f} "
              f"{st.median([d['ma'] for d in v])*1e6:>12.2f} "
              f"{st.median([d['mp'] for d in v])*1e6:>13.2f} "
              f"{st.median([d['tIter'] for d in v])*1e6:>9.2f} "
              f"{st.median([d['r'] for d in v]):>8.2f}")

print(f"\n{'='*96}")
print("★ 关键：绝对构造成本 vs 相对成本 r")
print(f"{'='*96}")
print("  r = tPCSetup / tIter ⇒ 若 tIter 也随 levels 变化，则 r 不能直接跨级比较。")

# L2 与 L5 的迭代数
print(f"\n  {'levels':>7} {'每步 3 次求解的 N 之和（中位）':>32}")
for lv, logp, csvp in [(2, "s2/log.s1", "s_k2_r1.csv"), (5, "l5/log.k1r1", "l5_k1_r1.csv")]:
    if not os.path.exists(logp):
        continue
    Ns = solves_for(logp)
    if Ns:
        print(f"  {lv:>7} {st.median(Ns):>32.1f}")

print(f"\n{'='*96}")
print("★ 每步总墙钟的估算：t_pcsetup + ΣN · tIter")
print(f"{'='*96}")
print(f"  {'levels':>7} {'t_pcsetup/µs':>13} {'ΣN(中位)':>10} {'tIter/µs':>10} "
      f"{'每步合计/µs':>12} {'相对 L0':>10}")

est = {}
for lv, logp, csvp in [(0, None, None), (2, "s2/log.s1", "s_k2_r1.csv"),
                       (5, "l5/log.k1r1", "l5_k1_r1.csv")]:
    if lv in by if 'by' in dir() else False:
        pass
    rows = None
    if csvp and os.path.exists(csvp):
        rows = load20(csvp)
    elif os.path.exists("bench_ilu_levels.csv"):
        rows = [d for d in by.get(lv, [])]
    if not rows:
        continue
    ts = st.median([d["tPCSetup"] for d in rows])
    ti = st.median([d["tIter"] for d in rows])
    Ns = solves_for(logp) if logp else None
    if Ns is None and lv == 0:
        # L0 无独立日志；用 L2 的 N 作上限估计并标注
        Ns = solves_for("s2/log.s1")
        note = " (N 借用 L2)"
    else:
        note = ""
    nmed = st.median(Ns) if Ns else 0
    tot = ts + nmed * ti
    est[lv] = tot
    rel = f"{(tot/est[0]-1)*100:+9.2f}%" if 0 in est else ""
    print(f"  {lv:>7} {ts*1e6:>13.1f} {nmed:>10.1f} {ti*1e6:>10.2f} "
          f"{tot*1e6:>12.1f} {rel:>10}{note}")

print(f"\n  ⚠️ 注意：上表每步合计用的是【每步重建】的代价，")
print(f"     而不同 levels 的 N 差异很大（强预条件子迭代少）。")
print(f"     比较 K 的优劣时，必须用【同一 levels 内】的实测 N，")
print(f"     绝不能跨 levels 借用 —— 本项目所有 K 扫描均已如此处理。")
