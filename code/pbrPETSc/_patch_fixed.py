#!/usr/bin/env python3
"""
修正 sim_fixed 的预热期语义。

★ bug：原实现用相位公式 a = (t - b0) % K 判重建，
   在预热期 t < b0 也会跳着复用。
   而 PBR 的真实语义是【b0 之前每步都重建】
   （见 PETScPreconditioner.C：timeIndex_ < b0 时 freezeAt_=-1 且 reusedFrom_=-1）。

   后果：固定周期基线被人为做便宜（省掉约 2/3 的预热期重建），
   导致 "固定周期优于 oracle" 这一逻辑上不可能的结论。

★ 正确实现（与原版 greedy_v6 一致）：
       if (t < b0) or ((t - b0) % K == 0): 重建
       else: 复用
"""
p = "online_cross.py"
s = open(p).read()

old = '''def sim_fixed(Nfn, r0, K, T, b0=100):
    tot = 0.0
    for t in range(1, T+1):
        a = (t - b0) % K
        nb = (a == 0)
        tot += (r0 + Nfn(t, 0)) if nb else Nfn(t, a)
    return tot'''

new = '''def sim_fixed(Nfn, r0, K, T, b0=100):
    """周期 K 的固定策略。

    ★ 语义必须与 PBR 实现一致：预热期 t < b0【每步都重建】，
      之后每 K 步重建一次（基步为 b0, b0+K, ...）。
    """
    tot = 0.0
    a = 0
    for t in range(1, T+1):
        if (t < b0) or ((t - b0) % K == 0):
            tot += r0 + Nfn(t, 0)
            a = 1
        else:
            tot += Nfn(t, a)
            a += 1
    return tot'''
assert old in s, "sim_fixed 未找到"
s = s.replace(old, new)
open(p, "w").write(s)
print("OK: sim_fixed 语义已修正")
