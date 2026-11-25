#!/usr/bin/env python3
"""
第二层最终裁决：实测 K* 系统性偏好更长周期 —— 反解隐含 ρ*

★ 已观察到的模式（5/5 配置）：
   实测最优 K* = K5（fx 例外为 K3），而模型在【标定 ρ】下给出 K3。
   这不是散乱的不一致，而是系统性的单向偏移（实测偏好更少重建）。

本脚本反解：使【模型 K* = 实测 K*】所需的 ρ 是多少？
   记 ρ* = 该反解值。比较 ρ* 与两个候选标定：
       下界 r1          （CSV 的 tPCSetup/tIter，"一次重建付一次分解"）
       上界 s·r1        （"一次重建付 s 次分解"，C++ 的 RCOST=step）

★ 若 ρ* 系统性落在 [r1, s·r1] 内且接近 s·r1，则
   (a) 我们的 ρ 区间假设得到独立实测支持；
   (b) 实测 K* 与模型 K* 的不一致【被解释】，不再是缺陷。

★ 硬约束：只用本批次（同轮交错）的墙钟排序定实测 K*，不跨批次比较。
"""
import sys, os, re, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import load_phase, Env, CFG, sim_fixed, P2

TAGS = {"fx": "k2fx", "l15": "k2l15", "fine": "k2fine",
        "l20": "k2l20", "x3": "k2x3"}
LOGRE = re.compile(r"round=(\d+) mode=(K\d) K=(\d+) wall_ms=(\d+) execTime=([\d.]+) "
                   r"iters=(\d+) nsteps=(\d+) rbsteps=(\d+)")


def read_batch(tag):
    f = "%s/%s.log" % (P2, tag)
    if not os.path.exists(f):
        return None
    out = {}
    for ln in open(f, errors="ignore"):
        m = LOGRE.search(ln)
        if not m:
            continue
        out.setdefault(m.group(2), []).append(int(m.group(4)))
    return out


def model_kstar(env, rho, T, B0, kmax):
    best, bc = None, None
    for k in range(1, kmax + 1):
        c = sim_fixed(env, rho, k, T, B0)[0]
        if bc is None or c < bc:
            best, bc = k, c
    return best


print("=" * 126)
print("★★★ 第二层最终裁决：反解隐含 ρ*（使模型 K* = 实测 K*）")
print("=" * 126)

rows = []
for name, tag in TAGS.items():
    b = read_batch(tag)
    if not b:
        print("\n【%s】本批次无数据" % name)
        continue
    d = load_phase(name)
    lvl, T, B0 = CFG[name]
    env = Env(d["tab"], sFact=d["s"])
    r1, s = d["r1"], d["s"]
    kmax = env.amax_data + 1

    # 实测 K*（本批次墙钟中位）
    med = {m: st.median(v) for m, v in b.items()}
    kmeas = int(min(med, key=med.get)[1:])
    second = sorted(med, key=med.get)[1]
    gap = 100.0 * (med[second] - med[min(med, key=med.get)]) / med[min(med, key=med.get)]
    rng = 100.0 * (max(b[min(med, key=med.get)]) - min(b[min(med, key=med.get)])) / med[min(med, key=med.get)]

    # 模型 K* 在标定 ρ 下
    kmod_cal = model_kstar(env, r1, T, B0, kmax)

    # 反解 ρ*：扫 ρ，找使模型 K* = kmeas 的最小 ρ
    rho_star = None
    lo, hi = 1.0, 3000.0
    for step in range(0, 3001):
        rho = lo + (hi - lo) * step / 3000.0
        if model_kstar(env, rho, T, B0, kmax) >= kmeas:
            rho_star = rho
            break

    print("\n" + "─" * 126)
    print("【%s】levels=%d T=%d  k_max=%d" % (name, lvl, T, kmax))
    print("  实测排序: %s"
          % " < ".join("%s(%.0f)" % (m, med[m]) for m in sorted(med, key=med.get)))
    print("  实测 K* = K%d （与次优差 %.2f%%，该模式轮间极差 %.1f%%）" % (kmeas, gap, rng))
    print("  模型 K* @ 标定ρ=%.1f → K%d" % (r1, kmod_cal))
    print("  模型 K* @ ρ=s·r1=%.1f → K%d" % (r1 * s, model_kstar(env, r1 * s, T, B0, kmax)))
    if rho_star is None:
        print("  ★ 反解失败：即使 ρ=3000 模型也不给 K%d" % kmeas)
    else:
        ratio = rho_star / r1
        print("  ★ 隐含 ρ* = %.1f（模型 K* 首次达到 K%d）" % (rho_star, kmeas))
        print("      ρ*/r1 = %.2f    s = %.2f    ρ*/(s·r1) = %.2f"
              % (ratio, s, rho_star / (r1 * s)))
        print("      ρ* 落在 [r1, s·r1] 内？ %s"
              % ("✓ 是" if r1 <= rho_star <= r1 * s else "★ 否（超出上界 %.0f%%）"
                 % (100.0 * (ratio - s) / s)))
    rows.append((name, kmeas, kmod_cal, r1, s, rho_star, gap, rng))

print("\n" + "=" * 126)
print("汇总")
print("=" * 126)
print("  %-6s %-6s %-14s %-9s %-9s %-11s %-10s %s"
      % ("配置", "实测K*", "模型K*@标定", "ρ*反解", "ρ*/r1", "ρ*/(s·r1)", "最优-次优", "轮间极差"))
for name, km, kc, r1, s, rs, gap, rng in rows:
    if rs is None:
        print("  %-6s K%-5d K%-13d %-9s %-9s %-11s %-10s %.1f%%" % (name, km, kc, "-", "-", "-", "%.2f%%" % gap, rng))
    else:
        print("  %-6s K%-5d K%-13d %-9.1f %-9.2f %-11.2f %-10s %.1f%%"
              % (name, km, kc, rs, rs / r1, rs / (r1 * s), "%.2f%%" % gap, rng))

rr = [x[5] / x[3] / x[4] for x in rows if x[5] is not None]
if rr:
    print("\n  ★ ρ*/(s·r1) 全体: %s   中位 %.2f"
          % (" ".join("%.2f" % v for v in rr), st.median(rr)))
if rows:
    g = [x[6] for x in rows]
    n = [x[7] for x in rows]
    print("  ★ 最优-次优差距 vs 轮间极差（信噪比）:")
    for name, km, kc, r1, s, rs, gap, rng in rows:
        print("     %-6s 差距 %.2f%%  噪声 %.1f%%  比值 %.2f"
              % (name, gap, rng, gap / rng if rng else 0))
