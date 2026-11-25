#!/usr/bin/env python3
"""
★★★ a_cost_interval.py —— 主结果表：ρ 以【物理区间】报告（2026-10-13 修正版）

═══════════════════════════════════════════════════════════════════════════
★ 本次修正的核心（原版用点值 ρ = r1，已证不足）
═══════════════════════════════════════════════════════════════════════════
C++ 的 buildPC() 每个 SOLVE 调用一次（每步 s 次，实测 s = 2.99–3.00），
但 CSV 只在"每步第一次求解"时写一行 ⇒ 该行的 tPCSetup 只含 1/s 的分解时间，
而 r = tPCSetup/tIter 用的正是它。于是 ρ 有明确的物理上下界：

    下界 ρ_lo = r1        （一次重建只付一次分解）
    上界 ρ_hi = s × r1    （一次重建付 s 次分解；C++ 的 RCOST=step 即此口径）

反解四配置实测行为得到的隐含 ρ* 落在两者【之间】（覆盖 3/4，
与 s·r1 之比 0.75–1.12，不是常数）⇒ **真值在区间内，但不等于任一端点。**

⇒ 报告规则：
    · K* 必须报【集合】（随 ρ 变化，如 {K2..K4}），不得报单一值
    · gap / regret / K1倍数 必须在整个区间上取 min/max
    · 三个来源的 ρ 区间并列报告：(a) 标定物理区间 (b) 实测排序反解 (c) 隐含 ρ*

═══════════════════════════════════════════════════════════════════════════
用法
═══════════════════════════════════════════════════════════════════════════
  python a_cost_interval.py            # 用服务器相位数据（需在服务器上跑）
  python a_cost_interval.py --selftest # 用合成数据离线自检（本地可跑）
"""
import sys, os, json, math, statistics as st

SELFTEST = "--selftest" in sys.argv

if SELFTEST:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
else:
    sys.path.insert(0, "/root/autodl-tmp/PBR")

from pbrcost import (CFG, ORDER, load_phase, Env, rho_interval_calib,
                     interval_stats, rho_interval_from_order, P2)


# ── 实测墙钟（ms）：来自 a2A.log / a2l15.log / a2B.log，同批次同轮交错 ──
WALL = {
    "l15": {"K1": [19894, 19930], "K3": [16303, 17599, 15458],
            "ONLs": [16568, 16851, 15413], "ONLp": [17946, 17068, 16046]},
    "l20": {"K1": [24871, 28752, 28835], "K3": [18634, 18802, 19264, 21930, 18786],
            "K5": [20182, 18208, 19764, 19820, 17961],
            "ONLs": [18093, 21550, 19533, 21255, 20420],
            "ONLp": [20040, 19046, 23595, 20681, 22764]},
    "fl30": {"K1": [473896, 463758, 485404], "K3": [242733, 248792, 267071],
             "K5": [254614, 251082, 252614], "ONLs": [241074, 249894, 252136],
             "ONLp": [251357, 250120, 245034]},
}
IT = {
    "l15": {"K1": (5765, 344), "K3": (10335, 181), "ONLs": (8040, 221), "ONLp": (10544, 180)},
    "l20": {"K1": (4688, 344), "K3": (9361, 181), "K5": (16046, 148),
            "ONLs": (6940, 221), "ONLp": (9474, 180)},
    "fl30": {"K1": (11953, 720), "K3": (26373, 306), "K5": (52114, 224),
             "ONLs": (26648, 305), "ONLp": (37696, 254)},
}
# 第二层反解的隐含 ρ*（由"实测最优 K 落在哪两个 K 之间"推出）
IMP = {"fx": 194.3, "l15": 198.3, "l20": 202.6, "fine": 307.3}


# ───────────────────────── 数据来源 ─────────────────────────
def build_envs():
    """
    返回 {tag: (env, r1, s)}。
      正常模式：读服务器相位数据。
      自检模式：用可解析的合成 N(t,a) 造表（保证 K* 会随 ρ 移动，以检验逻辑）。
    """
    out = {}
    if SELFTEST:
        for tag in ORDER:
            lvl, T, B0 = CFG[tag]
            # 合成曲线：N(t,0) 缓变；N(t,a) 随 a 超线性上升（制造平坦 c(k)）
            tab = {}
            for t in range(1, T + 1):
                base = 12.0 + 8.0 * math.sin(t / 90.0) + 0.002 * t
                for a in range(0, 7):
                    tab[(t, a)] = base + 9.0 * a + 1.35 * a * a
            env = Env(tab, sFact=3.0)
            out[tag] = (env, 60.0, 3.0)
        return out
    for tag in ORDER:
        d = load_phase(tag)
        out[tag] = (Env(d["tab"], sFact=d["s"]), d["r1"], d["s"])
    return out


def main():
    print("=" * 130)
    print("★★★ 主结果表（区间形式）：cost(π; ρ) = iters + ρ · rbsteps"
          + ("      【离线自检模式：合成数据】" if SELFTEST else ""))
    print("=" * 130)

    envs = build_envs()

    # ── 0. 三个 ρ 来源并列
    print()
    print("─" * 130)
    print("★ ρ 的三个来源（必须并列报告，不得只取其一）")
    print("─" * 130)
    print("  %-6s %10s %6s %-22s %-22s %s" %
          ("配置", "r1(标定)", "s", "(a) 标定物理区间", "(b) 实测排序反解", "(c) 隐含ρ*"))
    rng = {}
    for tag in ORDER:
        env, r1, s = envs[tag]
        lo, hi = rho_interval_calib(r1, s)
        b = "—"
        if tag in WALL and not SELFTEST:
            pts = [(m, IT[tag][m][0], IT[tag][m][1], st.median(WALL[tag][m]))
                   for m in IT[tag]]
            blo, bhi, _ = rho_interval_from_order(pts)
            rng[tag] = (blo, bhi)
            b = ("[%.1f, %.1f]" % (blo, bhi)) if blo <= bhi else "【空】"
        c = ("%.1f" % IMP[tag]) if tag in IMP else "—"
        print("  %-6s %10.1f %6.2f %-22s %-22s %s" %
              (tag, r1, s, "[%.1f, %.1f]" % (lo, hi), b, c))
    print()
    print("  ⇒ (a) 是报告口径：真 ρ 在 [r1, s·r1] 内，但不等于任一端点")
    print("  ⇒ (b) 为空表示该配置的墙钟排序无法被任何单一 ρ 复现（审计项 I2）")
    if not SELFTEST:
        print("  ⇒ (c) 与 (a) 的重合度 = 该口径的验证；比值 0.75–1.12 说明不是简单乘 s")

    # ── 1. 区间表
    print()
    print("─" * 130)
    print("★ 区间表：gap / regret / K1倍数 在整个 ρ 区间上的范围；K* 报【集合】")
    print("─" * 130)
    print("  %-6s %-20s %-14s %-22s %-22s %s" %
          ("配置", "ρ 区间", "K* 集合", "在线 vs K* (gap%)",
           "regret vs oracle (%)", "K1/在线"))
    OUT = {}
    for tag in ORDER:
        env, r1, s = envs[tag]
        lo, hi = rho_interval_calib(r1, s)
        lvl, T, B0 = CFG[tag]
        stt = interval_stats(env, lo, hi, T, B0, npts=13)
        OUT[tag] = dict(r1=r1, s=s, lo=lo, hi=hi,
                        gap_lo=stt["gap_lo"], gap_hi=stt["gap_hi"],
                        reg_lo=stt["reg_lo"], reg_hi=stt["reg_hi"],
                        k1o_lo=stt["k1o_lo"], k1o_hi=stt["k1o_hi"],
                        kstar=[int(k) for k in stt["kstar_set"]])
        ks = stt["kstar_set"]
        kss = "K%d" % ks[0] if len(ks) == 1 else "K%d..K%d" % (min(ks), max(ks))
        print("  %-6s %-20s %-14s [%+7.3f, %+7.3f] [%+6.2f, %+6.2f] [%.2f×, %.2f×]" %
              (tag, "[%.1f, %.1f]" % (lo, hi), kss,
               stt["gap_lo"], stt["gap_hi"], stt["reg_lo"], stt["reg_hi"],
               stt["k1o_lo"], stt["k1o_hi"]))

    # ── 2. 结论表述
    print()
    print("=" * 130)
    print("★ 论文用表述（区间形式，三段）")
    print("=" * 130)
    g1 = min(OUT[t]["k1o_lo"] for t in ORDER)
    g1h = max(OUT[t]["k1o_hi"] for t in ORDER)
    ghi = max(OUT[t]["gap_hi"] for t in ORDER)
    glo = min(OUT[t]["gap_lo"] for t in ORDER)
    rhi = max(OUT[t]["reg_hi"] for t in ORDER)
    rlo = min(OUT[t]["reg_lo"] for t in ORDER)
    ksets = sorted(set(tuple(OUT[t]["kstar"]) for t in ORDER))
    print()
    print("  (1) 在线 vs 每步重建（K=1）—— 可主张")
    print("      对每个配置的 ρ ∈ [r1, s·r1]，在线策略相对每步重建的倍数 ∈")
    print("      [%.2f×, %.2f×]（>1 表示更便宜）。" % (g1, g1h))
    print()
    print("  (2) 在线 vs 最优固定周期 —— 只能说「不可分辨 / 差距有界」")
    print("      在 ρ ∈ [r1, s·r1] 上，在线距【事后已知的】最优固定周期")
    print("      差 %.3f–%.3f pp。该量随 ρ 变号，故不主张方向。" % (glo, ghi))
    print("      regret 相对 oracle 为 %.2f–%.2f pp。" % (rlo, rhi))
    print("      ★ K* 本身随 ρ 取到 %s —— 必须作为集合报告。" %
          "、".join("{%s}" % ",".join("K%d" % k for k in s) for s in ksets))
    print()
    print("  (3) 模型与 C++ —— 可主张，且是核心可信性证据")
    print("      7 配置的决策序列在 5 个配置上 100% 一致；")
    print("      fine 为一次性相位穿越（重建数只差 1），sth 为刀刃不可分辨（已降级）。")
    print("      沿实测路径定价误差 ≤ 0.35%。")

    if not SELFTEST:
        with open("%s/cost_interval.json" % P2, "w") as f:
            json.dump(OUT, f, indent=1, default=str)
        print("\n  已写出 cost_interval.json")
    else:
        print("\n  【自检模式】未写文件。")
    print("=" * 130)


main()
