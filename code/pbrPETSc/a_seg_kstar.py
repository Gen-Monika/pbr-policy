#!/usr/bin/env python3
"""
★★★ a_seg_kstar.py —— 证据链 (a)：各配置在【前段/后段】分别在哪个 K 上最优

═══════════════════════════════════════════════════════════════════════
要回答什么
═══════════════════════════════════════════════════════════════════════
"免扫描"这一贡献的承重点是【最优周期会漂移 ⇒ 离线选定一次不够】。
已有证据只有 Stefan 一个配置（endTime=20→K=5；50/100→K=8–13）。
本脚本用【已有的相位扫描数据】检验：六个配置的 K* 是否在段间漂移。

═══════════════════════════════════════════════════════════════════════
方法（无新实验，纯查表）
═══════════════════════════════════════════════════════════════════════
对固定周期 K，第 t 步的年龄由周期表唯一确定，【与时间窗起点无关】：

    a_K(t) = 0                     若 t < B0 或 (t−B0) % K == 0
           = (t−B0) % K            否则

于是窗口 W 上的成本为

    cost_K(W) = Σ_{t∈W} N(t, a_K(t)) + ρ · |{t∈W : a_K(t)=0}|

★ K ≤ 6 ⇒ a_K(t) ≤ 5 ≤ amax_data ⇒ 全部落在实测覆盖内，【不外推】。

═══════════════════════════════════════════════════════════════════════
审计项
═══════════════════════════════════════════════════════════════════════
S1  段间 K* 是否漂移（前段 K* ≠ 后段 K*）
S2  漂移在 ρ 区间的两端是否都给同一结论（稳健性）
S3  漂移幅度是否超过噪声（用段内累计量的确定性判断，非墙钟）
S4  各段的 K* 处的成本优势（相对段内次优）有多少
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import (ORDER, CFG, load_phase, Env, rho_interval_calib)

KsAll = (1, 2, 3, 4, 5, 6)
SEGS = (2, 3)   # 分 2 段、3 段


def age_of(t, K, B0):
    if t < B0 or (t - B0) % K == 0: return 0
    return (t - B0) % K


def seg_cost(env, K, B0, w):
    """窗口 w（含端点列表 t）上固定周期 K 的 cost 与分量。"""
    it = 0.0; rb = 0
    for t in w:
        a = age_of(t, K, B0)
        it += env(t, a)
        if a == 0: rb += 1
    return it, rb


def main():
    print("=" * 128)
    print("★★★ 证据链 (a)：各配置在【前段 / 后段】的最优固定周期")
    print("=" * 128)
    print()
    print("  方法：对固定 K，a_K(t) 由周期表唯一确定（与窗口起点无关），")
    print("        cost_K(W) = Σ_{t∈W} N(t,a_K(t)) + ρ·|重建步|。K≤6 ⇒ 年龄≤5，全部实测覆盖。")
    print()

    drifted = []
    for tag in ORDER:
        d = load_phase(tag); lvl, T, B0 = CFG[tag]
        env = Env(d["tab"], sFact=d["s"])
        r1, sfac = d["r1"], d["s"]
        lo, hi = rho_interval_calib(r1, sfac)
        Ks = tuple(k for k in KsAll if k <= env.amax_data + 1)

        # 后预热区间 [B0, T]，按 t 切段
        allT = list(range(B0, T + 1))
        print("─" * 128)
        print("【%s】T=%d  B0=%d  后预热 %d 步   ρ ∈ [%.1f, %.1f]"
              % (tag, T, B0, len(allT), lo, hi))

        for nseg in SEGS:
            w = len(allT) // nseg
            segs = [allT[i * w:(i + 1) * w if i < nseg - 1 else len(allT)]
                    for i in range(nseg)]
            for lab, rho in (("ρ=r1", lo), ("ρ=s·r1", hi)):
                row = []
                for si, sw in enumerate(segs):
                    tot = {}
                    for K in Ks:
                        it, rb = seg_cost(env, K, B0, sw)
                        tot[K] = it + rho * rb
                    kb = min(tot, key=tot.get)
                    srt = sorted(tot, key=tot.get)
                    gain = 100.0 * (tot[srt[1]] - tot[kb]) / tot[srt[1]]
                    # 该段的时间范围（步号）
                    row.append((kb, tot[kb], gain, srt[1]))
                ks = [x[0] for x in row]
                drift = len(set(ks)) > 1
                if drift and nseg == 2 and lab == "ρ=r1":
                    drifted.append(tag)
                print("    %d 段 / %-8s : %s   %s"
                      % (nseg, lab,
                         "  ".join("第%d段 K*=%d(优势%.2f%%)" % (i + 1, x[0], x[2])
                                   for i, x in enumerate(row)),
                         "★ 漂移" if drift else "无漂移"))

        # 段的时间边界提示
        w2 = len(allT) // 2
        print("    （2 段的步号边界：前段 t=%d..%d，后段 t=%d..%d）"
              % (allT[0], allT[w2 - 1], allT[w2], allT[-1]))

    print()
    print("=" * 128)
    print("★ S1/S2 汇总：在 ρ=r1 口径、分 2 段时，K* 发生漂移的配置")
    print("   漂移配置：%s" % (drifted if drifted else "（无）"))
    print("   未漂移：%s" % [t for t in ORDER if t not in drifted])
    print("=" * 128)


main()
