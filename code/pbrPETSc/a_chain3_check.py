#!/usr/bin/env python3
"""
三环论证的证据核对：①不重建的后果 ②固定周期需要预扫描 ③在线逼近其收益

① 用实测的老化曲线（含"永不重建"运行）量化"不重建"的代价。
   关键数据：FREEZE_K=100000 ⇒ b=100 后永不重建，年龄达 244。
② 用第二层的扫描成本实测（16–18×）。
③ 用已验收的相位表 + ρ=r1 算 gap / regret。
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]
KS = (1, 2, 3, 4, 5, 6)

print("=" * 122)
print("★★★ 三环论证的证据核对")
print("=" * 122)

print("\n【环①】不重建的后果 —— 用实测老化曲线外推「永不重建」的代价")
print("  数据来源：phase scan 表（实测 N(t,a)）+ 已知的相变点")
print("  %-6s %-9s %-12s %-12s %-12s %s"
      % ("配置", "ρ=r1", "N(a=0)", "N(a=6)", "永不重建 avg N", "末段增量率"))

for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    # 永不重建：年龄从 1 一直涨到 T-B0
    a = 0
    tot = 0.0
    ages = []
    for t in range(1, T + 1):
        if t < B0:
            tot += env(t, 0); a = 1
        else:
            tot += env(t, a); a += 1
            ages.append(a)
    nbar = tot / T
    # 与最优固定周期比
    rho = d["r1"]
    bc, bk = min(((sim_fixed(env, rho, k, T, B0)[0], k) for k in KS if k <= env.amax_data + 1))
    # 末段增量率（a=5→6）
    n5, n6 = env(200, 5), env(200, 6)
    last = 100.0 * (n6 - n5) / n5 if n5 else float("nan")
    print("  %-6s %-9.1f %-12.0f %-12.0f %-12.1f %.1f%%/步   (noreb/最优固定 = %.2fx)"
          % (tag, rho, env(200, 0), env(200, 6), nbar, last, nbar / (bc / T)))

print("\n【环②】固定周期需要预扫描 —— 第二层实测")
print("  扫描成本 / 真实求解一遍：fx 16.5×  l15 17.6×  l20 16.9×  fine 18.5×")
print("  且 K* 不是 r 的函数（存在 r 更大而 K* 更小的反例）⇒ 每个新配置都要重扫")

print("\n【环③】在线策略逼近其收益 —— 相位表 + ρ=r1（已过实测裁判的口径）")
print("  %-6s %-11s %-11s %-11s %-11s %s"
      % ("配置", "在线 cost", "K* cost", "K=1 cost", "regret", "gap vs K*"))
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    rho = d["r1"]
    c, it, rb, _, _ = sim_online_detail(env, rho, T, B0)
    bc, bk = min(((sim_fixed(env, rho, k, T, B0)[0], k) for k in KS if k <= env.amax_data + 1))
    c1 = sim_fixed(env, rho, 1, T, B0)[0]
    print("  %-6s %-11.0f K%-2d %-8.0f %-11.0f %+8.2f%%  %+7.2f%%"
          % (tag, c, bk, bc, c1, 100.0 * (c - bc) / bc, 100.0 * (c - bc) / bc))
