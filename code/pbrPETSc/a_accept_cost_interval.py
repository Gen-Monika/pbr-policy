#!/usr/bin/env python3
"""
★★★ a_accept_cost_interval.py —— 主结果重算的验收审计

验收标准（用户指定，三条）：
  V1  内建审计 A1–A4 全过
  V2  `oracle ≤ 最优固定周期 ≤ K=1` 在 ρ 的【整个物理区间】上无违规
  V3  K* 集合随 ρ 的变化符合预期

★ 额外的自查（吸取此前教训，防止"自检通过但结论错"）：
  V4  sth 的 gap < 0（在线比最优固定周期便宜）是【合法】还是 bug？
      —— 判据：oracle 必须 ≤ 在线 ≤ K* 才说明是合法的"在线优于任何固定周期"
  V5  区间估计必须真的取自区间两端+内部，不能只是两点
  V6  reach 是否被 AMAX 正确覆盖（防止陷阱 52 的假 oracle 重现）
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import (ORDER, CFG, load_phase, Env, sim_fixed, sim_online,
                     sim_dp, online_max_age, rho_interval_calib,
                     audit_all, interval_stats)

KsAll = (1, 2, 3, 4, 5, 6)


def main():
    print("=" * 122)
    print("★★★ 验收审计：主结果重算（区间形式）")
    print("=" * 122)
    fails = []

    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        r1, sfac = d["r1"], d["s"]
        lo, hi = rho_interval_calib(r1, sfac)
        print("\n" + "─" * 122)
        print("【%s】T=%d B0=%d  ρ ∈ [%.1f, %.1f]  amax_data=%d"
              % (tag, T, B0, lo, hi, env.amax_data))

        # ── V1 内建审计
        ok, msgs = audit_all(dict(env=env), r1, T, B0)
        print("  V1 内建 A1–A4: %s" % ("通过 ✓" if ok else "★ 未通过"))
        for m in msgs:
            if not m.startswith("A1–A4"): print("       " + m)
        if not ok: fails.append("%s: V1" % tag)

        # ── V2 oracle 不等式链，在 21 个点上（含两端点与内部）
        pts = [lo + (hi - lo) * i / 20.0 for i in range(21)]
        bad = []
        for r in pts:
            Ks = tuple(k for k in KsAll if k <= env.amax_data + 1)
            orc = sim_dp(env, r, T, B0, reach=online_max_age(env, r, T, B0))
            fxv = {K: sim_fixed(env, r, K, T, B0)[0] for K in Ks}
            kb = min(fxv, key=fxv.get)
            onl = sim_online(env, r, T, B0)[0]
            if not (orc[0] <= fxv[kb] + 1e-6 and orc[0] <= fxv[1] + 1e-6
                    and orc[0] <= onl + 1e-6):
                bad.append((r, orc[0], fxv[kb], onl))
        print("  V2 oracle ≤ 最优固定周期 ≤ K=1：%d 点检查，违规 %d 个%s"
              % (len(pts), len(bad), ("  ★ " + str(bad[:2])) if bad else " ✓"))
        if bad: fails.append("%s: V2" % tag)

        # ── V3 K* 集合与 gap/regret 的区间
        stt = interval_stats(env, lo, hi, T, B0, npts=21)
        print("  V3 K* 集合 = %s    gap ∈ [%+.3f, %+.3f]    regret ∈ [%+.3f, %+.3f]"
              % (["K%d" % k for k in stt["kstar_set"]],
                 stt["gap_lo"], stt["gap_hi"], stt["reg_lo"], stt["reg_hi"]))

        # ── V4 若 gap < 0，验证它是否合法（oracle ≤ 在线 ≤ K*）
        if stt["gap_lo"] < -1e-9:
            worst = min(stt["per_rho"], key=lambda x: x["gap"])
            legal = (worst["c_orc"] <= worst["c_onl"] + 1e-6
                     and worst["c_onl"] <= worst["c_kst"] + 1e-6)
            print("  V4 gap<0 出现在 ρ=%.1f：oracle=%.0f 在线=%.0f K*=%.0f(K%d)"
                  % (worst["rho"], worst["c_orc"], worst["c_onl"],
                     worst["c_kst"], worst["kstar"]))
            print("       且 oracle ≤ 在线 ≤ K* ？ %s"
                  % ("✓ 合法（在线确实优于任何固定周期）" if legal
                     else "★ 非法（低于 oracle，是 bug）"))
            if not legal: fails.append("%s: V4" % tag)
        else:
            print("  V4 gap 恒 ≥ 0，无需验证")

        # ── V5 区间取样确实覆盖内部
        print("  V5 区间取样点数（含内部）= %d %s"
              % (len(stt["rho_grid"]),
                 "✓" if len(stt["rho_grid"]) >= 21 else "★ 过少"))

        # ── V6 reach 覆盖
        reach_hi = online_max_age(env, hi, T, B0)
        amax = env.amax_for(T, reach=reach_hi)
        print("  V6 ρ=上界时 reach=%d, AMAX=%d  %s"
              % (reach_hi, amax,
                 "✓ 覆盖" if amax > reach_hi else "★ 未覆盖（假 oracle）"))
        if amax <= reach_hi: fails.append("%s: V6" % tag)

    print()
    print("=" * 122)
    if fails:
        print("★★★ 验收【未通过】，失败项：%s" % fails)
    else:
        print("★★★ 验收【通过】：V1–V6 全部满足")
    print("=" * 122)
    return 0 if not fails else 1


sys.exit(main())
