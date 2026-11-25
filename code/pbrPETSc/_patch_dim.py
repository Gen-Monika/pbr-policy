#!/usr/bin/env python3
"""
修正 online_cross.py 的维度错误：不应把每步迭代数除以 s。

正确成本模型（与原版 greedy_v6 一致）：
    重建一步的成本 = r + N_step(0)
    复用一步的成本 = N_step(a)
其中 N_step = 该步 s 次求解的迭代数【之和】，r = tPCSetup/tIter
（r 是"以一次迭代为单位"的构造成本，而每步只有一次构造成本，
 因为快照每步只写一次、s 次求解共用）。

⇒ 判据为 ΔN_step(a) < r（不是 r/s）。
"""
p = "online_cross.py"
s = open(p).read()

# 1) build_config：去掉 / s
old = "                cells[(t, a)].append(Ns[i] / s)     # 单次求解的平均迭代数"
new = "                cells[(t, a)].append(Ns[i])          # ★ 每步 s 次求解的迭代数之和"
if old not in s:
    print("WARN: 未找到除法行，检查当前内容")
print("apply #1:", old in s)
s = s.replace(old, new)

# 2) 函数签名里的 s 不再用于缩放，但保留（用于打印核对 nSolve/nStep）
# 3) 文档字符串修正
s = s.replace(
    "三个指标（互为对照）：",
    "★ 维度约定：N 一律用【每步 s 次求解的迭代数之和】；r = tPCSetup/tIter。\n"
    "  判据 ΔN_step(a) < r。\n\n三个指标（互为对照）：")

open(p, "w").write(s)
print("OK")
