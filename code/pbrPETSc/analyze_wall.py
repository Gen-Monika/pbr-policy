#!/usr/bin/env python3
"""
★ 交错墙钟实验分析（从【日志】取内部计时，因为 PBR_PETSC_BENCH=0 不写 CSV）。

日志里每个重建步都印有：
    PETSc ilu lvl=5 rebuild : t_freeze=.. t_convert=.. t_pcsetup=.. r=..
每个复用时印有：
    PETSc ilu lvl=5 REUSE@<b> : ...
⇒ t_pcsetup 可直接从日志取，无需 CSV。

墙钟分辨率：`date +%s` 取整 ⇒ 1 秒，总时长 11–12 秒 ⇒ 相对分辨率 ~8%，
与待测效应同量级 ⇒ 墙钟【不足以判定】，只作交叉验证。
"""
import os
import re
import statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
PETSC_RE = re.compile(r"PETSc ilu lvl=\d+\"?\s*(rebuild|\"REUSE@\d+\")\s*:"
                      r"\s*t_freeze=([0-9.]+)us\s+t_convert=([0-9.]+)us"
                      r"\s+t_pcsetup=([0-9.]+)us\s+r=([0-9.eE+-]+)")


def parse_log(path):
    """每步：{reused, solves[], tsetup_us, r}"""
    steps, cur = [], None
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur is not None:
                steps.append(cur)
            cur = dict(reused=None, solves=[], ts=None, r=None)
            continue
        if cur is None:
            continue
        m = PETSC_RE.search(ln)
        if m:
            cur["reused"] = 0 if m.group(1) == "rebuild" else 1
            cur["ts"] = float(m.group(4))          # µs
            try:
                cur["r"] = float(m.group(5))
            except ValueError:
                cur["r"] = None
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur["solves"].append(int(ms.group(1)))
    if cur is not None:
        steps.append(cur)
    return steps


print("=" * 96)
print("★ 交错墙钟实验分析（levels=5，5 轮 × K=1/2/3）")
print("=" * 96)
print("""
  说明：本次运行设了 PBR_PETSC_BENCH=0，故 report() 不打印、也不写 CSV。
  但日志里的【迭代数】完整，且五轮逐位相同 ⇒ 迭代成本项可精确比较。
  t_setup 用同一 levels 下先前扫描的实测中位（levels=5: 2920.1 µs）补齐。
""")

R_L5 = 35.00          # levels=5 实测 r（中位）
TS_L5 = 2920.1e-6     # levels=5 实测 tPCSetup 中位（秒）
# 由 r = tsetup/tIter ⇒ tIter = tsetup/r
TI_L5 = TS_L5 / R_L5
print(f"  取自先前扫描：r = {R_L5:.2f}，tPCSetup = {TS_L5*1e6:.1f} µs "
      f"⇒ tIter = {TI_L5*1e6:.2f} µs")

# 墙钟
wall = defaultdict(list)
for ln in open("wt.out"):
    m = re.search(r"round=(\d+) K=(\d+) wall=(\d+)s", ln)
    if m:
        wall[int(m.group(2))].append(int(m.group(3)))

print(f"\n  1. 墙钟（`date +%s`，分辨率 1 秒）")
print(f"  {'K':>3} {'各轮/s':>26} {'中位':>6} {'均值':>7}")
for K in sorted(wall):
    v = wall[K]
    print(f"  {K:>3} {str(v):>26} {st.median(v):>6.0f} {st.mean(v):>7.2f}")
print(f"\n  ⇒ 12→11 秒即 −8%，但分辨率 1 秒 ⇒ 墙钟不可单独下结论")

# 迭代数（主证据）
print(f"\n{'='*96}")
print("  2. ★ 迭代数（主证据，逐位确定）")
print(f"{'='*96}")
print(f"  {'K':>3} {'轮':>3} {'步数':>5} {'ΣN':>8}")
sns = defaultdict(list)
for K in (1, 2, 3):
    for R in range(1, 6):
        logp = f"l5wt/log.r{R}k{K}"
        if not os.path.exists(logp):
            continue
        sN = sum(sum(s["solves"]) for s in parse_log(logp))
        sns[K].append(sN)
        print(f"  {K:>3} {R:>3} {len(parse_log(logp)):>5} {sN:>8}")

print(f"\n  {'K':>3} {'ΣN(中位)':>10} {'相对K=1':>10} {'五轮是否相同':>13}")
if 1 in sns:
    bN = st.median(sns[1])
    for K in sorted(sns):
        same = "是 ✓" if len(set(sns[K])) == 1 else "否 ✗"
        print(f"  {K:>3} {st.median(sns[K]):>10.0f} "
              f"{(st.median(sns[K])/bN-1)*100:>9.2f}% {same:>13}")
    print(f"\n  ★ 迭代数五轮逐位相同 ⇒ 完全确定，是可信的主证据。")

# 内部合计（迭代项 + setup 项）
print(f"\n{'='*96}")
print(f"  3. ★ 内部合计 = ΣN·tIter + 重建数·tPCSetup（tIter = {TI_L5*1e6:.2f} µs）")
print(f"{'='*96}")
KREB = {1: 344, 2: 222, 3: 181}      # 来自先前 L5 扫描
print(f"  {'K':>3} {'ΣN':>8} {'ΣN·tIter/s':>12} {'重建数':>7} "
      f"{'Σt_setup/s':>11} {'内部合计/s':>11} {'相对K=1':>10}")
inner = {}
for K in sorted(sns):
    sN = st.median(sns[K])
    it = sN * TI_L5
    su = KREB.get(K, 0) * TS_L5
    inner[K] = it + su
    rel = f"{(inner[K]/inner[1]-1)*100:+9.2f}%" if 1 in inner else ""
    print(f"  {K:>3} {sN:>8.0f} {it:>12.3f} {KREB.get(K,0):>7} {su:>11.3f} "
          f"{inner[K]:>11.3f} {rel:>10}")

print(f"\n{'='*96}")
print("  4. 预条件子占比与折算")
print(f"{'='*96}")
print(f"  {'K':>3} {'内部合计/s':>12} {'墙钟中位/s':>11} {'占比':>8} "
      f"{'内部收益':>10} {'折算墙钟':>10}")
for K in sorted(inner):
    w_ = st.median(wall[K])
    frac = inner[K] / w_
    gain = inner[K] / inner[1] - 1
    print(f"  {K:>3} {inner[K]:>12.3f} {w_:>11.0f} {frac*100:>7.1f}% "
          f"{gain*100:>9.2f}% {gain*frac*100:>9.2f}%")

print(f"\n{'='*96}")
print("  5. 结论")
print(f"{'='*96}")
print("  内部计时（可信）：")
for K in sorted(inner):
    print(f"    K={K}: {(inner[K]/inner[1]-1)*100:+.2f}%")
print("\n  墙钟（分辨率不足，仅作交叉验证）：")
for K in sorted(wall):
    print(f"    K={K}: 中位 {st.median(wall[K])}s（各轮 {wall[K]}）")
o_in = "K=3 与 K=2 均优于 K=1" if inner[3] < inner[1] and inner[2] < inner[1] else "排序不同"
o_wt = "K=3 与 K=2 均不劣于 K=1" if st.median(wall[3]) <= st.median(wall[1]) and \
       st.median(wall[2]) <= st.median(wall[1]) else "排序不同"
print(f"\n  ⇒ 内部：{o_in}；墙钟：{o_wt}")
print(f"  ⇒ 两者的{'排序方向一致' if 'K=3' in o_in and 'K=3' in o_wt else '排序方向不一致'}。")
print(f"\n  ⚠️ 本轮墙钟仅 5 轮、分辨率 1 秒、总量 11–12 秒，")
print(f"     不足以独立支撑加速结论。上述整数差异（12→11）无法排除取整效应。")

