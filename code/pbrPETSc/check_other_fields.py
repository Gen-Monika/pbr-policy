#!/usr/bin/env python3
"""
★ 零成本检查：非 p_rgh 场的求解器，其迭代数是否随 K 变化？

═══════════════════════════════════════════════════════════════════════
动机
═══════════════════════════════════════════════════════════════════════
同源实验（levels=10）显示：
  K=1 墙钟 15.68 s，其中预条件子相关仅 4.62 s，未解释 11.06 s
  K=3 墙钟 12.33 s，其中预条件子相关 3.96 s，未解释  8.37 s

已确认：各 K 的时间步序列【完全相同】（Time = 逐行一致），
        每次压力求解的迭代数也【按 K 确定性】。

⇒ 那么逐步的物理过程应当相同 ⇒ "其他部分"的耗时也应当相同。
   但实测未解释量随 K 变化（11.06 → 8.37 → 8.47）⇒ 必有一项随 K 变化。

★ 本脚本检查最可能的候选：其他场的求解器迭代数。

若 alpha.water / k / epsilon / pcorr 的迭代数随 K 变化，
则它们的耗时也变 ⇒ 可解释"未解释量"的大部分。
"""
import os
import re
import statistics as st
from collections import defaultdict

# 匹配："<solver>:  Solving for <field>, ... No Iterations <N>"
SOLVE_RE = re.compile(
    r"^(\w[\w-]*)\s*:\s+Solving for (\w[\w.]*),\s+Initial residual = ([0-9.eE+-]+),"
    r"\s+Final residual = ([0-9.eE+-]+),\s+No Iterations\s+(\d+)")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")


def field_stats(path):
    """返回 {field: (样本数, Σ迭代数, 迭代数列表)}"""
    out = defaultdict(lambda: [0, [], 0])   # field -> [count, iters, sum]
    for ln in open(path, errors="ignore"):
        m = SOLVE_RE.match(ln)
        if not m:
            continue
        solver, field, ir, fr, it = m.groups()
        rec = out[field]
        rec[0] += 1
        rec[1].append(int(it))
        rec[2] += int(it)
    return out


print("=" * 100)
print("★ 非 p_rgh 场的迭代数是否随 K 变化？（levels=10，同源实验）")
print("=" * 100)

data = {}
for K in (1, 2, 3, 5, 8):
    path = f"samesrc/log.r1k{K}"
    if not os.path.exists(path):
        continue
    data[K] = field_stats(path)

if not data:
    print("  （无数据）")
    raise SystemExit

# 收集所有场名
fields = set()
for K in data:
    fields |= set(data[K].keys())

print(f"\n  出现的场：{sorted(fields)}")

# ── 每个场在各 K 下的统计 ──
print(f"\n{'='*100}")
print("1. 每场在各 K 下的总迭代数")
print(f"{'='*100}")
print(f"  {'场':>14} " + "".join(f"{'K='+str(K):>12}" for K in sorted(data))
      + f"{'跨K是否相同':>14}")
same_all = {}
for f in sorted(fields):
    line = f"  {f:>14} "
    vals = []
    for K in sorted(data):
        rec = data[K].get(f)
        vals.append(rec[2] if rec else 0)
        line += f"{vals[-1]:>12}"
    same = len(set(vals)) == 1
    same_all[f] = same
    line += f"{'相同 ✓' if same else '不同 ✗':>14}"
    print(line)

# ── 若不相同的，逐段展示 ──
print(f"\n{'='*100}")
print("2. ★ 迭代数随 K 变化的场，逐段对比")
print(f"{'='*100}")
for f in sorted(fields):
    if same_all.get(f):
        continue
    print(f"\n  ── {f} ──")
    print(f"  {'K':>3} {'样本数':>7} {'Σ迭代':>8} {'中位':>7} {'最大':>7}")
    for K in sorted(data):
        rec = data[K].get(f)
        if not rec:
            print(f"  {K:>3} {'(无)':>7}")
            continue
        print(f"  {K:>3} {rec[0]:>7} {rec[2]:>8} "
              f"{st.median(rec[1]):>7.0f} {max(rec[1]):>7}")
    # 与 K=1 的差
    if 1 in data and data[1].get(f):
        base = data[1][f][2]
        print(f"    相对 K=1：", end="")
        for K in sorted(data):
            rec = data[K].get(f)
            if rec:
                print(f"K={K}:{(rec[2]/base-1)*100:+.2f}% ", end="")
        print()

print(f"\n{'='*100}")
print("3. ★ 判定")
print(f"{'='*100}")
changed = [f for f in sorted(fields) if not same_all.get(f)]
if not changed:
    print("""  ⇒ 所有场的迭代数在所有 K 下【完全相同】。
  ⇒ 因此"未解释量随 K 变化"不能由其他求解器的迭代数解释。
  ⇒ 剩下的可能：服务器效率波动（与 K 无关的随机漂移），
     或某种与重建次数相关的底层效应。""")
else:
    print(f"  ⇒ 以下场的迭代数随 K 变化：{changed}")
    print(f"  ⇒ 这些场的耗时变化可解释部分未解释量。")
    # 粗估：假设每迭代成本与 p_rgh 同量级（仅作数量级参考）
    print(f"""
  ⚠️ 注意：这些场用 smoothSolver（每迭代成本远低于 PCG+ILU），
     故其迭代数的变化对总耗时的影响需另测。""")

print(f"\n{'='*100}")
print("4. 附：每场的求解次数（应全部相同）")
print(f"{'='*100}")
print(f"  {'场':>14} " + "".join(f"{'K='+str(K):>10}" for K in sorted(data)))
for f in sorted(fields):
    line = f"  {f:>14} "
    for K in sorted(data):
        rec = data[K].get(f)
        line += f"{rec[0] if rec else 0:>10}"
    print(line)
