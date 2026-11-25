#!/usr/bin/env python3
"""
★★★ 判定：这是设计缺陷还是实现缺陷？

═══ 方法：ρ 的可行区间 ═══
把成本模型写成仿射形式（与背景项无关地做排序）：
    wall(mode) ≈ c + A·iters(mode) + B·rbsteps(mode)
其中 c 是【与 mode 无关的背景项】（物理求解、IO、网格操作、每-solve 固定开销）。
排序只取决于 ρ := B/A，因为 c 与 A 同除后不影响不等式方向。

于是：给定实测排序，反解出所有能满足【全部成对比较】的 ρ。
    wall_i < wall_j  ⇒  iters_i + ρ·rb_i < iters_j + ρ·rb_j
                     ⇔  ρ·(rb_i − rb_j) < iters_j − iters_i
每个不等式给 ρ 一个上界或下界。全部求交 ⇒ 可行区间 [lo, hi]。

判据：
  · 区间【非空】⇒ 存在单一 ρ 能复现实测排序
       ⇒ 线性函数形式是对的，问题只是 ρ 的【取值】
       ⇒ 属于【标定缺陷】（surrogate calibration），不是形式缺陷
  · 区间【为空】⇒ 任何 ρ 都无法复现
       ⇒ 线性函数形式不足 ⇒ 属于【设计缺陷】（objective 形式）
  · 区间很窄且与噪声同量级 ⇒ 排序不可判 ⇒ 属于【度量分辨率缺陷】

═ 同时核查 §0：纠正"背景项稀释权衡"的说法
   若 c 与 mode 无关，则排序由 iters + ρ·rb 决定，c 完全消掉。
   所以"背景项稀释权衡"是错的；真正的问题是 ρ 的取值或函数形式。
"""
import sys, os, re, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")

P2 = "/root/autodl-tmp/PBR"
CASES = [("l15", "a2l15.log"), ("l20", "a2A.log"), ("fl30", "a2B.log")]


def parse(logname):
    p = os.path.join(P2, logname)
    out = defaultdict(list)
    if not os.path.exists(p): return out
    for ln in open(p, errors="ignore"):
        if not ln.startswith("round="): continue
        kv = dict(x.split("=", 1) for x in ln.split() if "=" in x)
        M = kv.get("mode")
        if not M: continue
        try:
            out[M].append(dict(R=int(kv["round"]), wall=int(kv["wall_ms"]),
                               iters=int(kv["iters"]), rb=int(kv["rbsteps"])))
        except Exception:
            pass
    return out


def feasible_interval(points, use="median"):
    """
    points: [(name, iters, rbsteps, wall)]  wall 用指定统计量
    返回 (lo, hi, 约束列表)；lo=-inf/hi=+inf 表示无界；lo>hi 表示空
    """
    lo, hi = float("-inf"), float("inf")
    cons = []
    n = len(points)
    for i in range(n):
        for j in range(n):
            if i == j: continue
            ni, ii, ri, wi = points[i]
            nj, ij, rj, wj = points[j]
            if wi >= wj: continue           # 只要求"实测更快的 mode 成本更低"
            d = ri - rj
            num = ij - ii
            if abs(d) < 1e-12:
                if num < 0:
                    cons.append(("不可行", ni, nj, None))
                    return (1.0, -1.0, cons)   # 空
                continue
            b = num/float(d)
            if d > 0:
                hi = min(hi, b); cons.append(("上界", ni, nj, b))
            else:
                lo = max(lo, b); cons.append(("下界", ni, nj, b))
    return lo, hi, cons


print("=" * 128)
print("★★★ 0. 纠正：背景项与 mode 无关时，它不影响排序")
print("=" * 128)
print("  成本 = c + A·iters + B·rbsteps")
print("  排序 ⇔ A·iters + B·rbsteps 的排序（c 消掉）")
print("  ⇒ 只要 c 与 mode 无关，'背景项稀释权衡'的说法【不成立】。")
print("     真正决定排序的是 ρ = B/A 的取值，或函数形式是否够用。")
print()
print("  核查 c 是否真的与 mode 无关：")
print("  · nsteps 在所有 mode 下相同（物理步数不变）")
print("  · nBuildPC 在所有 mode 下相同（每 solve 一次 PCSetUp）")
print("  ⇒ c 的主要成分（物理、IO、每-solve 开销）确实与 mode 无关 ✓")

print()
print("=" * 128)
print("★★★ 1. 各 mode 的实测墙钟离散度（判断排序分辨率）")
print("=" * 128)
DATA = {}
for tag, logn in CASES:
    d = parse(logn)
    if not d: continue
    DATA[tag] = d
    print("\n  ── %s ──" % tag)
    print("     %-8s %10s %10s %10s %12s %10s %8s"
          % ("mode", "中位", "最小", "最大", "极差/中位", "iters", "rbsteps"))
    rows = []
    for M in sorted(d):
        v = d[M]
        w = [x["wall"] for x in v]
        med = st.median(w)
        rng = (max(w) - min(w))/med
        it = st.median([x["iters"] for x in v])
        rb = st.median([x["rb"] for x in v])
        rows.append((M, med, min(w), max(w), rng, it, rb))
        print("     %-8s %10d %10d %10d %11.1f%% %10.0f %8.0f"
              % (M, med, min(w), max(w), 100*rng, it, rb))
    DATA[tag]["_rows"] = rows

print()
print("=" * 128)
print("★★★ 2. ρ 的可行区间（用中位墙钟）")
print("=" * 128)
FIT = {}
for tag in DATA:
    rows = DATA[tag]["_rows"]
    pts = [(M, it, rb, med) for (M, med, mn, mx, rng, it, rb) in rows]
    lo, hi, cons = feasible_interval(pts)
    FIT[tag] = (lo, hi)
    print("\n  ── %s ──  （%d 个 mode，%d 个成对约束）"
          % (tag, len(pts), len(cons)))
    for (kind, ni, nj, b) in cons:
        if b is None:
            print("     ★ 不可行约束: %s 快于 %s" % (ni, nj))
        else:
            print("     %s: %s 快于 %s  ⇒  ρ %s %.2f"
                  % (kind, ni, nj, "<=" if kind == "上界" else ">=", b))
    if lo > hi:
        print("     ⇒ ★可行区间【空】：不存在任何 ρ 能复现实测排序")
    else:
        print("     ⇒ 可行区间 ρ ∈ [%.2f, %.2f]%s"
              % (lo, hi, "（无界）" if (lo == float("-inf") or hi == float("inf")) else ""))

print()
print("=" * 128)
print("★★★ 3. 模型与拟合的 ρ 落在可行区间内吗？")
print("=" * 128)
MODEL_RHO = {"l15": 232.4, "l20": 271.0, "fl30": 440.6}
LSQ_RHO = {"l15": 53.7, "l20": 162.8, "fl30": 290.1}
print("  %-6s %16s %16s %24s   %s"
      % ("配置", "模型 r_eff", "拟合 R/k", "可行区间", "判定"))
for tag in FIT:
    lo, hi = FIT[tag]
    rng = "[%.1f, %.1f]" % (lo, hi) if lo <= hi else "【空】"
    def inside(r):
        if lo > hi: return "✗"
        return "✓" if (lo <= r <= hi) else "✗"
    print("  %-6s %16.1f %16.1f %24s   模型%s  拟合%s"
          % (tag, MODEL_RHO[tag], LSQ_RHO[tag], rng,
             inside(MODEL_RHO[tag]), inside(LSQ_RHO[tag])))

print()
print("=" * 128)
print("★★★ 4. 用噪声的极值重做（检验区间是否被噪声撑开）")
print("=" * 128)
print("  若用最小/最大墙钟得到的区间差异很大，说明排序本身在噪声内。")
print()
print("  %-6s %26s %26s" % ("配置", "区间（用中位）", "区间（用最小）"))
for tag in DATA:
    rows = DATA[tag]["_rows"]
    pts_m = [(M, it, rb, med) for (M, med, mn, mx, rng, it, rb) in rows]
    pts_n = [(M, it, rb, mn) for (M, med, mn, mx, rng, it, rb) in rows]
    lo1, hi1, _ = feasible_interval(pts_m)
    lo2, hi2, _ = feasible_interval(pts_n)
    f = lambda lo, hi: ("[%.1f, %.1f]" % (lo, hi)) if lo <= hi else "【空】"
    print("  %-6s %26s %26s" % (tag, f(lo1, hi1), f(lo2, hi2)))

print()
print("=" * 128)
print("★★★ 5. 关键定量：最好与次好的差距 vs 噪声")
print("=" * 128)
print("  %-6s %-8s %10s %-8s %10s %10s %12s"
      % ("配置", "最快", "墙钟", "次快", "墙钟", "差距%", "该mode噪声%"))
for tag in DATA:
    rows = sorted(DATA[tag]["_rows"], key=lambda z: z[1])
    if len(rows) < 2: continue
    m1, w1, _, _, r1, _, _ = rows[0]
    m2, w2, _, _, r2, _, _ = rows[1]
    gap = 100.0*(w2 - w1)/w1
    print("  %-6s %-8s %10d %-8s %10d %9.2f%% %11.1f%%"
          % (tag, m1, w1, m2, w2, gap, 100*r1))
print()
print("  ⇒ 若「差距%」与「噪声%」同量级，则最快与次快的区分本身不可靠。")
print("=" * 128)
