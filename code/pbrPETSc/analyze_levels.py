#!/usr/bin/env python3
"""
ILU 填充层级的 r（14 列旧格式）。

列义（由恒等式 r = tPCSetup/tIter 反推校验）：
  1 timeIndex 2 field 3 kind 4 levels 5 nCells 6 nFaces 7 reps
  8 tConvert  9 tPCSetup 10 ma 11 mp 12 tIter 13 r 14 rTotal

校验（第 1 行）：
  r      = 0.00221425/7.52602e-05 = 29.42  ✓ (文件 29.4212)
  rTotal = (0.0024637+0.00221425)/7.52602e-05 = 62.16  ✓ (文件 62.157)
"""
import os
import statistics as st
from collections import defaultdict

HDR14 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,"
         "tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")

if not os.path.exists("bench_ilu_levels.csv"):
    print("bench_ilu_levels.csv 不存在")
    raise SystemExit

by = defaultdict(list)
bad = 0
for ln in open("bench_ilu_levels.csv"):
    p = ln.rstrip("\n").split(",")
    if len(p) != 14:
        continue
    try:
        d = dict(zip(HDR14, p))
        lv = int(float(d["levels"]))
        tc, ts = float(d["tConvert"]), float(d["tPCSetup"])
        ti = float(d["tIter"])
        rv, rt = float(d["r"]), float(d["rTotal"])
    except ValueError:
        continue
    if ti <= 0:
        continue
    # 恒等式校验
    if abs(ts / ti - rv) > 1e-2 or abs((tc + ts) / ti - rt) > 1e-2:
        bad += 1
        continue
    by[lv].append(dict(r=rv, rTotal=rt, ts=ts, ti=ti, tc=tc))

print("=" * 90)
print("ILU 填充层级的 r 实测（列义已由两条恒等式校验）")
print("=" * 90)
print(f"  恒等式校验不通过的行: {bad}")

print(f"\n  {'levels':>7} {'样本':>6} {'r 中位':>10} {'r 均值':>10} "
      f"{'r 范围':>18} {'tPCSetup中位/µs':>16}")
for lv in sorted(by):
    v = by[lv]
    rs = [d["r"] for d in v]
    ts = st.median([d["ts"] for d in v])
    print(f"  {lv:>7} {len(v):>6} {st.median(rs):>10.2f} {st.mean(rs):>10.2f} "
          f"{f'[{min(rs):.1f}, {max(rs):.1f}]':>18} {ts*1e6:>16.1f}")

# 只统计真正重建的（排除复用时 ~1µs 的残留：filter ts > 100µs）
print(f"\n  ── 只看真正分解的样本（tPCSetup > 100 µs）──")
print(f"  {'levels':>7} {'样本':>6} {'r 中位':>10} {'tPCSetup中位/µs':>16} {'tIter中位/µs':>14}")
clean = {}
for lv in sorted(by):
    v = [d for d in by[lv] if d["ts"] > 1e-4]
    if not v:
        continue
    rs = [d["r"] for d in v]
    clean[lv] = rs
    print(f"  {lv:>7} {len(v):>6} {st.median(rs):>10.2f} "
          f"{st.median([d['ts'] for d in v])*1e6:>16.1f} "
          f"{st.median([d['ti'] for d in v])*1e6:>14.2f}")

# 门限
print("\n" + "=" * 90)
print("门限对照")
print("=" * 90)
print("  门限 r > ΔN_step(1)。实测 ΔN_step(1)：")
print("    步段 101-150 : 38.0")
print("    步段 151-200 : 19.0")
print("    步段 201-250 : 16.0")
print("    步段 251-300 : 22.0")
print("    步段 301-344 : 16.0")
print()
for lv in sorted(clean):
    m = st.median(clean[lv])
    print(f"  levels={lv}: r = {m:6.2f}  ⇒ "
          f"{'全时段可复用 ✓' if m > 38 else ('后期可复用 ✓' if m > 22 else '仅最有利段可复用' if m>16 else '处处重建 ✗')}")

# 每步 3 次求解的换算
print("\n" + "=" * 90)
print("每步 3 次求解时的有效门限")
print("=" * 90)
print("  判据等价形式：ΔN_single < r/3")
print("  ΔN_single 实测 ≈ 10.7（= 38/3 附近），故需要 r/3 > 10.7 ⇒ r > 32")
print()
for lv in sorted(clean):
    m = st.median(clean[lv])
    print(f"  levels={lv}: r/3 = {m/3:6.2f}  vs ΔN_single≈10.7  ⇒ "
          f"{'✓ 门限越过' if m/3 > 10.7 else '✗ 未越过'}")
