#!/usr/bin/env python3
"""
决定性对照：v3 的「7/7 优于固定周期」在【相位扫描 N 表 + 形状迁移外推】下是否成立？

★ 我先前的一次对照得到「0/7」，但那次有两个错误，不能作为反证：
   错误一：只用单一变体（P0），而 v3 是【在训练轮上从 8 个变体中选最优】。
   错误二：用了 pbrcost 的相位表，而 v3 用的是旧 K 扫描表 + 最近邻回退。
   ⇒ 那次差异混了两个变量，无法归因。

本脚本把协议对齐到 v3：
   · 同样做「留一轮」折叠选 K* 与在线变体
   · 同样用 8 个变体
   · 只把 N 表换成 pbrcost 的相位扫描表（形状迁移外推）
   · ρ 用 r_eff = s·r1（与 v3 的 COSTMODE=step 一致）

结果解读：
   若仍 7/7 ⇒ 结论对 N 表口径稳健，可直接进论文
   若 <7/7 ⇒ N 表口径是决定因素，必须查清哪个是对的
"""
import sys, sys as _s, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail

VARIANTS = [("P0",    dict()),                       # 基线：无 target/force，lvl=last
            ("A6",    dict()), ("A8", dict())]        # amax 变体在 Env 里没有对应旋钮，跳过

# ★ Env 只实现了 P0（严格因果）。要复现 v3 的 8 变体需要 pbrlib 的完整实现。
#   本脚本先只做 P0，但【明确标注】这是与 v3 协议的一处不对齐。
VARIANTS = [("P0", dict())]

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]
KS = (1, 2, 3, 4, 5, 6)

print("=" * 118)
print("对照：相位扫描 N 表 + 形状迁移外推 + ρ=s·r1，协议与 v3 对齐（除变体数）")
print("=" * 118)
print("  ⚠️ 本脚本只用 P0 单变体（Env 无 target_age/force_every 旋钮），")
print("     故它【不是】v3 的完整复现，而是「单变体 + 相位表」这一格的单独测量。\n")
print("  %-6s %-10s %-12s %-12s %-10s %s"
      % ("配置", "ρ=s·r1", "在线 cost", "最优固定K", "gap", "在线更优?"))

wins = 0
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    rho = d["r1"] * d["s"]
    c, it, rb, _p, _m = sim_online_detail(env, rho, T, B0)
    bc, bk = min(((sim_fixed(env, rho, k, T, B0)[0], k)
                  for k in KS if k <= env.amax_data + 1))
    gap = 100.0 * (c - bc) / bc
    wins += (1 if gap < 0 else 0)
    print("  %-6s %-10.1f %-12.0f K=%-10d %+8.2f%%  %s"
          % (tag, rho, c, bk, gap, "✓" if gap < 0 else "★ 否"))
print("\n  ⇒ 单变体(P0) + 相位表 + ρ=s·r1：在线更优 %d/7" % wins)
