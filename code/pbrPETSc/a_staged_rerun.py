#!/usr/bin/env python3
"""
在【已验收的相位扫描表】上重跑 Stage D 的启发式对照。

★ 为什么必须重跑：Stage D 原版用的是旧 K 扫描表 + 最近邻插值，
  那张表复现 C++ 实测决策只有 31–66%；而已验收的相位表为 100%（5/7 配置）。
  Stage D 的核心结论（在线 0/7 输给 REAC）建立在被弃用的表上。

本脚本实现三条规则（均可忠实实现）：
  · Chalmers      max(factor·k₀, floor)          绝对阈值，锚在 k₀ 上
  · REAC_PRECOND  迭代数 > reac 则重分解           绝对阈值，固定整数
  · 20% 相对阈值   相对基线涨超 20% 则重建          相对阈值
并给出：本文在线策略、K=1、事后最优 K*、DP oracle 的对照。
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed, sim_online_detail, sim_dp

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]
KS = (1, 2, 3, 4, 5, 6)


def sim_chalmers(env, T, B0, rho, factor=2.0, floor=10.0):
    tot = 0.0; a = 0; k0 = None; nrb = 0
    for t in range(1, T + 1):
        N = env(t, 0 if a == 0 else a)
        if t < B0 or a == 0:
            rebuild = True
        else:
            thr = max(factor * (k0 if k0 else N), floor)
            rebuild = N > thr
        if rebuild:
            k0 = env(t, 0)
            tot += rho + k0; a = 1; nrb += 1
        else:
            tot += N; a += 1
    return tot, nrb


def sim_reac(env, T, B0, rho, reac=120.0):
    tot = 0.0; a = 0; nrb = 0
    for t in range(1, T + 1):
        if t < B0 or a == 0:
            rebuild = True
        else:
            rebuild = env(t, a) > reac
        if rebuild:
            tot += rho + env(t, 0); a = 1; nrb += 1
        else:
            tot += env(t, a); a += 1
    return tot, nrb


def sim_ratio(env, T, B0, rho, frac=0.20):
    tot = 0.0; a = 0; nrb = 0; base = None
    for t in range(1, T + 1):
        if t < B0 or a == 0:
            rebuild = True
        else:
            rebuild = (env(t, a) - base) / base > frac
        if rebuild:
            base = env(t, 0)
            tot += rho + base; a = 1; nrb += 1
        else:
            tot += env(t, a); a += 1
    return tot, nrb


print("=" * 130)
print("★ 已验收相位表上的启发式对照（ρ = r₁）")
print("=" * 130)
print("  %-6s %-10s %-11s %-11s %-11s %-11s %-11s %s"
      % ("配置", "K=1", "Chalmers", "REAC(120)", "20%规则", "最优K*", "本文在线", "oracle"))

rows = []
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    rho = d["r1"]
    # oracle（AMAX 给足，见 Stage D 的修复）
    orc = sim_dp(env, rho, T, B0)[0]
    c1 = sim_fixed(env, rho, 1, T, B0)[0]
    cch, _ = sim_chalmers(env, T, B0, rho)
    crc, _ = sim_reac(env, T, B0, rho, 120.0)
    crt, _ = sim_ratio(env, T, B0, rho, 0.20)
    bc, bk = min(((sim_fixed(env, rho, k, T, B0)[0], k) for k in KS if k <= env.amax_data + 1))
    con, _, _, _, _ = sim_online_detail(env, rho, T, B0)
    def rg(x): return 100.0 * (x - orc) / orc
    rows.append((tag, bk, rg(c1), rg(cch), rg(crc), rg(crt), rg(bc), rg(con)))
    print("  %-6s %-10.2f %-11.2f %-11.2f %-11.2f K%-10d %-11.2f %.0f"
          % (tag, rg(c1), rg(cch), rg(crc), rg(crt), bk, rg(con), orc))

print()
print("  ★ regret 范围（相对各自 oracle，%）：")
for i, lab in ((2, "K=1"), (3, "Chalmers"), (4, "REAC(120)"), (5, "20%规则"), (6, "最优K*"), (7, "本文在线")):
    v = [r[i] for r in rows]
    print("     %-12s [%.2f%%, %.2f%%]   中位 %.2f%%" % (lab, min(v), max(v), st.median(v)))

print()
print("  ★ 在线策略逐配置胜负（regret 更小者胜）：")
for lab, idx in (("Chalmers", 3), ("REAC(120)", 4), ("20%规则", 5), ("最优K*", 6)):
    w = sum(1 for r in rows if r[7] < r[idx])
    print("     在线 vs %-12s : %d/%d" % (lab, w, len(rows)))
