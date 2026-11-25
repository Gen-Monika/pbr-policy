#!/usr/bin/env python3
"""
★★★ a_rho_corrected.py —— 用修正后的 ρ 重算，检验是否与实测 K 偏好一致

★ 修正来源（见 docs/rho_underestimation_code_evidence_2026-10-13.md）：
  C++ 的 buildPC() 每个 SOLVE 调用一次（每步 s=3 次），但 CSV 只在"每步第一次求解"
  时写一行，所以该行的 tPCSetup 只含 1/3 的分解时间。
  ⇒ 标定 ρ = tPCSetup/tIter 低估了重建的真实代价；
  ⇒ 真 ρ 应为 s × 标定（C++ 的 RCOST=step 分支就是这么算的）。

★ 检验（不预设修正一定对）：
  T1  修正后，模型 K* 是否从 K2/K3 移到 K4/K5，与实测偏好（fx→K3, l15→K5,
      l20→K5, fine→K5）一致？
  T2  修正后，各配置的隐含 ρ*（由实测最优 K 反解）是否被 [标定, s×标定] 覆盖？
  T3  主结果表（在线 vs K* vs oracle）在修正后如何变化？

用法：python a_rho_corrected.py
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import (ORDER, CFG, load_phase, Env, sim_fixed, sim_online,
                     sim_dp, online_max_age)

# 第二层实测：墙钟最优 K 与最优-次优差距
MEAS_K = {   # tag -> (实测最优K, 次优K, 差距%, 该模式轮间极差%)
    "fx":   (3, 5, 3.59, 22.9),
    "l15":  (5, 3, 3.15, 27.0),
    "l20":  (5, 3, 1.39, 6.7),
    "fine": (5, 4, 3.26, 8.2),
}
# 第二层实测：隐含 ρ*
IMP = {"fx": 194.3, "l15": 198.3, "l20": 202.6, "fine": 307.3}

KsAll = (1, 2, 3, 4, 5, 6)


def best_k(env, rho, T, B0):
    c = {K: sim_fixed(env, rho, K, T, B0)[0] for K in KsAll if K <= env.amax_data + 1}
    return min(c, key=c.get), c


def main():
    print("=" * 124)
    print("★★★ ρ 修正的验证：真 ρ = s × 标定 ρ？")
    print("=" * 124)

    # ── T1 模型 K* 是否移向实测偏好
    print()
    print("─" * 124)
    print("★ T1：模型 K* 在 ρ 取不同口径时的位置（对照第二层实测的最优 K）")
    print("─" * 124)
    print("  %-6s %8s %6s | %-26s | %-26s | %s" %
          ("配置", "标定ρ", "s", "未修正(ρ=标定) K*(cost)",
           "修正后(ρ=s×标定) K*(cost)", "实测最优K"))
    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        r1, s = d["r1"], d["s"]
        kb0, _ = best_k(env, r1, T, B0)
        kb1, _ = best_k(env, r1 * s, T, B0)
        mk = MEAS_K.get(tag)
        mstr = ("K%d" % mk[0]) if mk else "—"
        flag = ""
        if mk:
            flag = "  ✓ 一致" if kb1 == mk[0] else ("  ~ 相邻" if abs(kb1 - mk[0]) == 1 else "  ★ 不一致")
        print("  %-6s %8.1f %6.2f | %-26s | %-26s | %s%s" %
              (tag, r1, s, "K%d (%.0f)" % (kb0, best_k(env, r1, T, B0)[1][kb0]),
               "K%d (%.0f)" % (kb1, best_k(env, r1 * s, T, B0)[1][kb1]), mstr, flag))

    # ── T2 隐含 ρ* 是否被 [标定, s×标定] 覆盖
    print()
    print("─" * 124)
    print("★ T2：实测反解的隐含 ρ* 是否落在 [标定ρ, s×标定ρ] 内")
    print("─" * 124)
    print("  %-6s %10s %12s %12s %s" %
          ("配置", "隐含ρ*", "区间下界", "区间上界", "是否覆盖"))
    cov = 0
    for tag in IMP:
        d = load_phase(tag); r1, s = d["r1"], d["s"]
        lo, hi = r1, r1 * s
        ip = IMP[tag]
        ok = lo <= ip <= hi
        cov += 1 if ok else 0
        print("  %-6s %10.1f %12.1f %12.1f %s" %
              (tag, ip, lo, hi, "✓ 是" if ok else "★ 否"))
    print("  ⇒ %d/%d 个配置的隐含 ρ* 被 [标定, s×标定] 覆盖" % (cov, len(IMP)))

    # ── T3 主结果表在修正前后的变化
    print()
    print("─" * 124)
    print("★ T3：主结果（在线 vs K* vs oracle）在修正前后的变化")
    print("─" * 124)
    print("  %-6s %8s | %-30s | %-30s" %
          ("配置", "口径", "K* / 在线 / oracle（cost）", "在线 gap vs K* / regret"))
    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        r1, s = d["r1"], d["s"]
        for lab, rho in (("未修正", r1), ("修正", r1 * s)):
            kb, c = best_k(env, rho, T, B0)
            onl = sim_online(env, rho, T, B0)[0]
            orc = sim_dp(env, rho, T, B0, reach=online_max_age(env, rho, T, B0))[0]
            gap = 100.0 * (onl / c[kb] - 1.0)
            reg = 100.0 * (onl / orc - 1.0)
            print("  %-6s %8s | K%-4d %9.0f %9.0f | %+8.3f%% %+8.2f%%" %
                  (tag, lab, kb, c[kb], onl, gap, reg))
        print()

    print("=" * 124)


main()
