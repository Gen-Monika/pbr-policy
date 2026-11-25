#!/usr/bin/env python3
"""
★★★ levels=10 严格交错墙钟实验分析（毫秒级）

═══════════════════════════════════════════════════════════════════════
为什么这次可信
═══════════════════════════════════════════════════════════════════════
1. 毫秒级计时（date +%s%3N），而非此前的 date +%s（1 秒分辨率）
2. 严格交错：每轮内轮流跑 K=1/2/3，共 6 轮 ⇒ 机器状态漂移被对称化
3. levels=10 的 tPCSetup = 8516 µs，占比远高于 L5 的 18.2%
4. 用 OpenFOAM 自报的 ExecutionTime 作主口径（不含进程启动/网格构建开销）

主口径 = ExecutionTime（求解器自报），
辅助口径 = wall_ms（含 blockMesh/setFields 与启动）。
"""
import os
import re
import statistics as st
from collections import defaultdict

print("=" * 100)
print("★★★ levels=10 严格交错墙钟分析")
print("=" * 100)

rowspat = re.compile(
    r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+steps=(\d+)")

wall = defaultdict(list)
exec_ = defaultdict(list)
rounds = defaultdict(dict)

for ln in open("l10wt.out"):
    m = rowspat.search(ln)
    if not m:
        continue
    R, K = int(m.group(1)), int(m.group(2))
    w, e = int(m.group(3)), float(m.group(4))
    wall[K].append(w)
    exec_[K].append(e)
    rounds[K][R] = (w, e)

print(f"\n  原始数据（{len(next(iter(rounds.values())))} 轮 × 3 个 K）")
print(f"  {'K':>3} {'各轮 ExecutionTime/s':>40} {'中位':>7}")
for K in sorted(exec_):
    print(f"  {K:>3} {str(exec_[K]):>40} {st.median(exec_[K]):>7.2f}")

N = len(next(iter(rounds.values())))
print(f"\n{'='*100}")
print("1. ★ 逐轮对照（交错的核心价值：同轮内比较，消除漂移）")
print(f"{'='*100}")
print(f"  {'轮':>3} {'K=1':>9} {'K=2':>9} {'K=3':>9} "
      f"{'K2 vs K1':>10} {'K3 vs K1':>10} {'K2 胜?':>8} {'K3 胜?':>8}")
w1 = w2 = w3 = 0
for R in range(1, N + 1):
    a = rounds[1][R][1]
    b = rounds[2][R][1]
    c = rounds[3][R][1]
    d2 = (b / a - 1) * 100
    d3 = (c / a - 1) * 100
    w1 += (b < a)
    w2 += (c < a)
    print(f"  {R:>3} {a:>9.2f} {b:>9.2f} {c:>9.2f} "
          f"{d2:>9.2f}% {d3:>9.2f}% {'是' if b < a else '否':>8} "
          f"{'是' if c < a else '否':>8}")
print(f"\n  ⇒ K=2 优于 K=1 的轮数：{w1}/{N}")
print(f"  ⇒ K=3 优于 K=1 的轮数：{w2}/{N}")

print(f"\n{'='*100}")
print("2. ★★ 汇总（主口径：ExecutionTime）")
print(f"{'='*100}")
print(f"  {'K':>3} {'中位/s':>9} {'均值/s':>9} {'最小':>8} {'最大':>8} "
      f"{'相对K=1(中位)':>14}")
base = st.median(exec_[1])
for K in sorted(exec_):
    med = st.median(exec_[K])
    print(f"  {K:>3} {med:>9.2f} {st.mean(exec_[K]):>9.2f} "
          f"{min(exec_[K]):>8.2f} {max(exec_[K]):>8.2f} "
          f"{(med/base-1)*100:>13.2f}%")

print(f"\n  {'K':>3} {'中位/ms':>10} {'均值/ms':>10} {'相对K=1':>10}")
bw = st.median(wall[1])
for K in sorted(wall):
    print(f"  {K:>3} {st.median(wall[K]):>10.0f} {st.mean(wall[K]):>10.1f} "
          f"{(st.median(wall[K])/bw-1)*100:>9.2f}%")

print(f"\n{'='*100}")
print("3. ★ 与内部计时模型的一致性检验")
print(f"{'='*100}")
print("""
  内部计时预测（levels=10，来自 analyze_l10.py）：
    K=1: cost = 27890.4
    K=2: cost = 22754.0   ⇒ 相对 K=1 = -18.42%
    K=3: cost = 22989.1   ⇒ 相对 K=1 = -17.57%
""")
pred = {1: 27890.4, 2: 22754.0, 3: 22989.1}
print(f"  {'K':>3} {'内部预测':>10} {'墙钟实测':>10} {'差异':>9} {'一致性':>8}")
for K in sorted(exec_):
    p = (pred[K] / pred[1] - 1) * 100
    m_ = (st.median(exec_[K]) / base - 1) * 100
    diff = m_ - p
    ok = "✓" if abs(diff) < 8 else "✗"
    print(f"  {K:>3} {p:>9.2f}% {m_:>9.2f}% {diff:>+8.2f}% {ok:>8}")

print(f"\n{'='*100}")
print("4. ★★ 预条件子占比的实测推算")
print(f"{'='*100}")
print("""
  由 τ_measured = τ_total × (1 + gain_internal)
  其中 τ_total = 包含全部重建的耗时，gain_internal = 内部计时给出的相对收益。
  ⇒ 可反解出"被优化的部分"占总耗时的比例。
""")
for K in (2, 3):
    g = pred[K] / pred[1] - 1              # 内部收益（负值）
    obs = st.median(exec_[K]) / base - 1   # 墙钟收益（负值）
    if g != 0:
        frac = obs / g
        print(f"  K={K}: 内部收益 {g*100:+.2f}%，墙钟收益 {obs*100:+.2f}% "
              f"⇒ 占比 ≈ {frac*100:.1f}%")

print(f"\n{'='*100}")
print("5. 统计显著性（样本仅 %d 轮，谨慎解读）" % N)
print(f"{'='*100}")
for K in (2, 3):
    diffs = [rounds[K][R][1] - rounds[1][R][1] for R in range(1, N + 1)]
    m = st.mean(diffs)
    sd = st.pstdev(diffs) if len(diffs) > 1 else 0.0
    se = sd / (len(diffs) ** 0.5) if len(diffs) > 1 else 0.0
    t = m / se if se > 0 else float("nan")
    print(f"  K={K} vs K=1：逐轮差的均值 = {m:+.3f}s，SD = {sd:.3f}，"
          f"SE = {se:.3f}，t = {t:.2f}")
print("""
  ⚠️ 逐轮配对差的正负方向一致（见 §1）比 t 统计量更能说明问题，
     因为样本量小且机器状态可能非独立。
""")
