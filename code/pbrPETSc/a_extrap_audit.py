#!/usr/bin/env python3
"""
★★★ a_extrap_audit.py —— 主结果对外推数据的依赖度审计

═══════════════════════════════════════════════════════════════════════
动机
═══════════════════════════════════════════════════════════════════════
N(t,a) 表里，年龄 a ≤ amax_data(=6) 的格子是**相位扫描实测**的；
a > 6 的格子是**形状迁移外推**（G(a) = curve(a)/curve(0)，末端线性延伸）。

外推本身就是一个"老化假设"。若某个配置的结果大量落在 a > 6 上，
那条结果就是靠假设撑起来的，必须显式标注或补测。

═══════════════════════════════════════════════════════════════════════
要回答的三个问题
═══════════════════════════════════════════════════════════════════════
E1  在 ρ = 实测标定值时，各配置的【在线策略】有多少步、多少代价落在 a > 6？
E2  同样的问题对【DP oracle】—— 它的决策空间由 AMAX 决定，可能走得很老。
E3  【最优固定周期 K*】的年龄上界是多少？（固定周期 K 的年龄最大到 K-1）

判定线：若某配置在 E1 上占比 < 1%，则它的主结果基本不依赖外推，可放心引用；
若占比可观（> 5%），则该配置需要补测或降级表述。
═══════════════════════════════════════════════════════════════════════
"""
import sys
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import (ORDER, CFG, load_phase, Env, sim_fixed, sim_dp,
                     sim_online_detail, online_max_age, _rows, _per_step_N)

# 实测标定值（r1 = median(tPCSetup/tIter)）
CAL = {"fx": 57.9, "l15": 77.7, "l20": 90.6, "fine": 115.2,
       "x3": 113.2, "fl30": 147.4, "sth": 17.0}

THRESH = 1.0   # % —— 占比低于此值即认为不依赖外推


def path_ages(pred, T):
    """由逐步动作序列还原逐步年龄。"""
    ages = []; held = -1
    for t in range(1, T + 1):
        if pred[t - 1]:
            ages.append(0); held = t
        else:
            ages.append(t - held)
    return ages


def main():
    print("=" * 118)
    print("★★★ 外推依赖度审计：主结果里有多少落在【未实测】的年龄上（a > amax_data）")
    print("=" * 118)

    print("\n  %-6s %6s %8s %10s %12s %12s %12s" %
          ("配置", "amax", "ρ标定", "在线maxA", "在线外推步%", "在线外推代价%", "判决"))
    verdict = {}
    detail = {}

    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        rho = CAL[tag]
        amax = env.amax_data

        # ── E1 在线策略
        cost, it, rb, pred, mv = sim_online_detail(env, rho, T, B0)
        ages = path_ages(pred, T)
        n_ex = sum(1 for a in ages if a > amax)
        cost_ex = sum(mv[i] for i in range(T) if ages[i] > amax)
        pct_step = 100.0 * n_ex / T
        pct_cost = 100.0 * cost_ex / max(1.0, it)

        ok = pct_cost < THRESH
        verdict[tag] = ok
        detail[tag] = dict(amax=amax, rho=rho, maxage=max(ages),
                           n_ex=n_ex, pct_step=pct_step,
                           cost_ex=cost_ex, pct_cost=pct_cost,
                           iters=it, rb=rb, online_cost=cost)

        print("  %-6s %6d %8.1f %10d %11.2f%% %11.3f%%  %s" %
              (tag, amax, rho, max(ages), pct_step, pct_cost,
               "✓ 不依赖外推" if ok else "★ 依赖外推"))

    # ── E2 oracle 的运行区间
    print()
    print("─" * 118)
    print("★ E2：DP oracle 的决策空间（reach=在线最大年龄 ⇒ AMAX 会被抬高）")
    print("─" * 118)
    print("  %-6s %10s %10s %14s %14s" %
          ("配置", "在线maxA", "AMAX", "oracle步数@a>6", "oracle代价%"))
    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        rho = CAL[tag]; amax = env.amax_data
        reach = online_max_age(env, rho, T, B0)
        orc = sim_dp(env, rho, T, B0, reach=reach)
        p = orc[3]
        oages = path_ages([x[1] == "R" for x in p], T)
        n_oex = sum(1 for a in oages if a > amax)
        c_oex = 0.0
        held = -1
        for t in range(1, T + 1):
            a = oages[t - 1]
            if a > amax: c_oex += env(t, a)
        print("  %-6s %10d %10d %14d %13.2f%%" %
              (tag, reach, env.amax_for(T, reach=reach), n_oex,
               100.0 * c_oex / max(1.0, orc[1])))

    # ── E3 K* 的年龄上界
    print()
    print("─" * 118)
    print("★ E3：ρ=标定值时最优固定周期 K* 的年龄上界（K* 的年龄最大到 K*-1）")
    print("─" * 118)
    print("  %-6s %8s %14s %14s" % ("配置", "K*", "K*最大年龄", "是否 ≤ amax(6)"))
    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        rho = CAL[tag]
        Ks = tuple(k for k in (1, 2, 3, 4, 5, 6, 8, 10, 13, 20, 30)
                   if k <= env.amax_data + 1)
        fxv = {K: sim_fixed(env, rho, K, T, B0)[0] for K in Ks}
        kb = min(fxv, key=fxv.get)
        mx = kb - 1
        print("  %-6s %8s %14d %14s" %
              (tag, "K%d" % kb, mx, "✓ 实测覆盖" if mx <= env.amax_data
               else "★ 超出"))

    # ── 判决
    print()
    print("=" * 118)
    bad = [t for t in ORDER if not verdict[t]]
    good = [t for t in ORDER if verdict[t]]
    if not bad:
        print("★ 判决：七个配置的在线策略代价值【全部】落在实测年龄范围内 —— "
              "主结果不依赖形状迁移外推。")
    else:
        print("★ 判决：以下配置的在线策略依赖外推数据，需要显式标注或补测：")
        for t in bad:
            dd = detail[t]
            print("   %-5s 年龄达 %d（实测只到 %d），外推步 %d 步（%.2f%%），"
                  "贡献 %.3f%% 的迭代代价"
                  % (t, dd["maxage"], dd["amax"], dd["n_ex"],
                     dd["pct_step"], dd["pct_cost"]))
    print("=" * 118)


main()
