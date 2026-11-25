#!/usr/bin/env python3
"""
决定性测试：v3 的协议 + 【相位扫描表】（已验收的 N 表）。

四轴差异：
   A1  N 表：v3 用旧 K 扫描表；验收过的是相位扫描表
   A2  插值：v3 的 mk 用最近邻；pbrcost 的 Env 用形状迁移
   A3  策略族：v3 从 8 个变体中在训练轮上选优；单一判据是 P0
   A4  ρ：r_solve  vs  r_eff = s·r_solve

v3 原样复现 7/7；强制 A3=P0 后 6/7。

本脚本：保留 A3（8 变体选择）与 A4（r_eff），
       把 A1/A2 换成相位表 + 形状迁移，看结果落在哪里。
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]
KS = (1, 2, 3, 4, 5, 6)

print("=" * 118)
print("★ 决定性测试：相位扫描表（形状迁移）+ 单变体 P0 + ρ=s·r1")
print("   与 v3 的 7/7、v3-强制P0 的 6/7 对照")
print("=" * 118)
print("  %-6s %-10s %-11s %-11s %-11s %-10s %s"
      % ("配置", "ρ=s·r1", "在线 cost", "最优固定K", "固定 cost", "gap", "在线更优?"))

wins = 0
rows = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    rho = d["r1"] * d["s"]
    c, it, rb, _, _ = sim_online_detail(env, rho, T, B0)
    bc, bk = min(((sim_fixed(env, rho, k, T, B0)[0], k)
                  for k in KS if k <= env.amax_data + 1))
    gap = 100.0 * (c - bc) / bc
    wins += (1 if gap < 0 else 0)
    rows.append((tag, rho, c, bk, bc, gap, it, rb))
    print("  %-6s %-10.1f %-11.0f K=%-9d %-11.0f %+8.2f%%  %s"
          % (tag, rho, c, bk, bc, gap, "✓ 优" if gap < 0 else "★ 劣"))

print("\n  ⇒ 相位表 + P0 + ρ=s·r1：在线更优 %d/7" % wins)
print()
print("  ★ 三口径对照：")
print("     v3 原样（旧表 + 最近邻 + 8变体 + r_eff）  → 7/7")
print("     v3 强制 P0（旧表 + 最近邻 + P0 + r_eff）   → 6/7")
print("     本行（相位表 + 形状迁移 + P0 + r_eff）      → %d/7" % wins)
print()
print("  ⇒ 若本行为 0，则「优于固定周期」这一主张依赖【旧表 + 变体选择】两处，")
print("     而在已验收的表与已锁定的判据下不成立。")
