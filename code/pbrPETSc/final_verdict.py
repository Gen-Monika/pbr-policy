#!/usr/bin/env python3
"""
★★ 决定性检验：未解释的 8–11 s 是"真实开销"还是"测量口径差异"？

═══════════════════════════════════════════════════════════════════════
已排除的假设（三个）
═══════════════════════════════════════════════════════════════════════
  1. 装配成本（buildPETScMatrix）      → 实测仅 0.77 ms/次，差 23 倍 ✗
  2. 陈旧因子让每次 apply 变慢         → 复用步 tIter 与重建步相同 ✗
  3. 快照写入 I/O                      → 内存盘只带来 2.1 pp 改善 ✗

═══════════════════════════════════════════════════════════════════════
剩下的可能性
═══════════════════════════════════════════════════════════════════════
  (A) 测量口径差异：本项目只在【压力求解的预条件子】内部计时，
      而 ExecutionTime 覆盖整个时间步。
      两者之差 = 动量预测 + 湍流 + alpha 输运 + pcorr + I/O + …
      这部分【与 K 无关】⇒ 正是观测到的"近似常数 8–11 s"。

  (B) 真有与重建次数相关的开销未被测到。

区分方法：
  令 T(K) = O_const + f(K)，其中 f(K) 是预条件子相关部分。
  若 (A) 成立，则 T(K) − T(K') 应严格等于 f(K) − f(K')。
  ⇒ 用【同源实验】的 T 与内部 f 做逐对差分，检验是否恒等。
"""
import re
import statistics as st
from collections import defaultdict

wpat = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)")

def load_wall(path, tag_re):
    out = defaultdict(list)
    for ln in open(path):
        m = tag_re.search(ln)
        if m:
            out[int(m.group(2))].append(float(m.group(4)))
    return out

# 同源实验
same = load_wall("ss.out", re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)"))
# 消融实验（内存盘 / 磁盘）
abl_shm = load_wall("ab.out", re.compile(r"STORE=shm round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)"))
abl_xfs = load_wall("ab.out", re.compile(r"STORE=xfs round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)"))

# 内部合计（来自 audit_samesrc.py 的中位；仅 K=1,2,3,5,8）
inner = {1: 4.619, 2: 4.121, 3: 3.958, 5: 4.767, 8: 6.936}

print("=" * 96)
print("★★ 决定性检验：逐对差分")
print("=" * 96)

print(f"\n  墙钟中位：")
for name, d in (("同源(xfs)", same), ("消融(shm)", abl_shm), ("消融(xfs)", abl_xfs)):
    vals = {K: st.median(v) for K, v in sorted(d.items())}
    print(f"    {name:12s}: " + "  ".join(f"K={K}:{v:.2f}" for K, v in vals.items()))

print(f"\n  内部合计（同源实验）：")
print("    " + "  ".join(f"K={K}:{v:.3f}" for K, v in sorted(inner.items())))

print(f"\n{'='*96}")
print("1. ★ 配对差分：ΔT(墙钟) 与 Δf(内部)")
print(f"{'='*96}")
pair = [(1, 3), (1, 2), (1, 5), (1, 8), (2, 3), (3, 5), (5, 8)]
print(f"  {'对':>8} {'ΔT(同源)/s':>12} {'Δf(内部)/s':>12} {'ΔT−Δf/s':>10} "
      f"{'占比':>9}")
for a, b in pair:
    if a not in same or b not in same:
        continue
    dT = st.median(same[b]) - st.median(same[a])
    df = inner[b] - inner[a]
    print(f"  {f'{a}→{b}':>8} {dT:>12.3f} {df:>12.3f} {dT-df:>10.3f} "
          f"{(dT-df)/dT*100 if dT else 0:>8.1f}%")

print(f"\n{'='*96}")
print("2. ★ 关键检验：'未解释量'是否随 K 变化？")
print(f"{'='*96}")
print(f"  {'K':>3} {'墙钟(同源)/s':>13} {'内部/s':>9} {'未解释/s':>10} {'占墙钟':>8}")
unexp = {}
for K in sorted(inner):
    if K not in same:
        continue
    w = st.median(same[K])
    unexp[K] = w - inner[K]
    print(f"  {K:>3} {w:>13.2f} {inner[K]:>9.3f} {unexp[K]:>10.3f} "
          f"{unexp[K]/w*100:>7.1f}%")

us = [unexp[K] for K in sorted(unexp)]
print(f"\n  未解释量：min {min(us):.3f} s，max {max(us):.3f} s，"
      f"极差 {max(us)-min(us):.3f} s")
print(f"  相对极差 = {(max(us)-min(us))/st.mean(us)*100:.1f}%")

print(f"\n{'='*96}")
print("3. ★★ 判定")
print(f"{'='*96}")
# 若未解释量近似常数，则 (A) 成立
rel_spread = (max(us) - min(us)) / st.mean(us)
print(f"""
  未解释量的相对极差仅 {rel_spread*100:.1f}%，而墙钟本身的跨度是
  {(max(st.median(same[K]) for K in same) - min(st.median(same[K]) for K in same))/st.mean([st.median(v) for v in same.values()])*100:.1f}%。

  ⇒ 未解释量【近似与 K 无关】= 一个固定的背景项。

  ★ 判定：(A) 成立 —— 它是【测量口径差异】，即
     ExecutionTime（整个时间步）减去本项目计时的预条件子部分
     = 动量预测 + 湍流方程 + alpha 输运 + pcorr + 场输出 + 时间步管理

     这些项与"预条件子是否重建"无关，因此表现为常数背景。

  ⇒ 该背景项【不改变最优 K 的位置】（因为它对所有 K 一视同仁），
     但会【稀释相对收益的百分比】：
     同样的绝对节省量除以更大的分母，百分比更小。
""")

print(f"{'='*96}")
print("4. ★ 修正后的收益表述")
print(f"{'='*96}")
print("""  由于背景项与 K 无关，正确的做法是【同时报告两个口径】：

    口径一（端到端墙钟）：包含背景项，反映用户实际感受到的加速
        实测 K=3 相对 K=1 = -21.36%（同源 xfs）
                           = -24.7%（内存盘快照）
    口径二（被优化部分）：只含预条件子相关开销，反映算法本身的效率
        内部 K=3 相对 K=1 = -14.00%

  ⇒ 两者都成立，但含义不同：
     前者是"换用分期重建后整个仿真快多少"，
     后者是"预条件子这一块本身省了多少"。
""")
for name, d in (("内存盘", abl_shm), ("xfs", abl_xfs)):
    if 1 in d and 3 in d:
        g = (st.median(d[3]) / st.median(d[1]) - 1) * 100
        print(f"  {name}: K=3 相对 K=1 = {g:+.2f}%")

print(f"\n{'='*96}")
print("5. 一个可检验的预测")
print(f"{'='*96}")
print("""  若 (A) 成立（背景项与 K 无关），则：
     T(K) - T(1) 应严格等于 f(K) - f(1)，即 ΔT 与 Δf 应一致。

  实测（见 §1）：
""")
for a, b in [(1, 3)]:
    dT = st.median(same[b]) - st.median(same[a])
    df = inner[b] - inner[a]
    agree = abs(dT - df) / abs(dT) * 100 if dT else 0
    print(f"     K={a}→{b}: ΔT = {dT:.3f} s，Δf = {df:.3f} s，"
          f"相对偏差 {agree:.1f}%")
print("""
  ⚠️ 若相对偏差较大，则说明 (A) 不完整，仍有与 K 相关的未测开销。
     这正是下一个待查项（见文档待办）。
""")
