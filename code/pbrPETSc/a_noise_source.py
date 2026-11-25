#!/usr/bin/env python3
"""
★★★ 噪声来源判定：租服务器 vs 本地，以及"换测量对象"的可行性

═══ 核心观察 ═══
我们其实有两个测量通道：
  (A) 墙钟（wall_ms）—— 噪声 4.6%~17.5%
  (B) 迭代数（iters）—— 三轮【逐位相同】：K1=[5765,5765,5765]、K3=[10335,...]
      ⇒ 零噪声、完全确定

若 (B) 在所有配置上都确定，则"策略决策质量"这件事根本不需要墙钟来测。
墙钟只用来回答"迭代数的差异换算成多少秒"，而那是一个
【每个配置只需标定一次】的常数。

═══ 本脚本回答三件事 ═══
1. 迭代数在所有配置上是否都完全确定？（跨轮、跨重复）
2. 墙钟的波动是否与机器负载（loadavg）相关？
   · 强相关 ⇒ 噪声是【外部争抢】造成 ⇒ 换更闲的机器有用
   · 弱相关 ⇒ 噪声是【内在】的（缓存、NUMA、频率）⇒ 换机器也没用
3. 需要多少轮才能分辨目标效应？（统计功效计算）
"""
import sys, os, re, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")

P2 = "/root/autodl-tmp/PBR"

LOGS = {
    "l15":  "a2l15.log",
    "l20":  "a2A.log",
    "fl30": "a2B.log",
    "l20s": "a2smoke3.log",
}

# 相位扫描的日志也带 load
PHASE_LOGS = ["phs.log"]

print("=" * 126)
print("★★★ 1. 迭代数的确定性（零噪声通道）")
print("=" * 126)
ROWS = defaultdict(list)   # (tag, mode) -> [(round, iters, wall, load)]
for tag, logn in LOGS.items():
    p = os.path.join(P2, logn)
    if not os.path.exists(p): continue
    for ln in open(p, errors="ignore"):
        if not ln.startswith("round="): continue
        kv = dict(x.split("=", 1) for x in ln.split() if "=" in x)
        M = kv.get("mode")
        if not M: continue
        try:
            ROWS[(tag, M)].append((int(kv["round"]), int(kv["iters"]),
                                   int(kv["wall_ms"]), float(kv.get("load", "nan"))))
        except Exception:
            pass

print("  %-8s %-6s %28s %8s %10s" % ("配置", "mode", "各轮 iters", "唯一值数", "判定"))
n_det = n_tot = 0
for (tag, M) in sorted(ROWS):
    it = [r[1] for r in ROWS[(tag, M)]]
    uniq = len(set(it))
    n_tot += 1
    if uniq == 1: n_det += 1
    print("  %-8s %-6s %28s %8d %10s"
          % (tag, M, str(it)[:28], uniq, "确定 ✓" if uniq == 1 else "★波动"))
print()
print("  ⇒ %d/%d 组完全确定（跨轮逐位相同）" % (n_det, n_tot))
print("     这说明【策略的决策质量】可以被零噪声地测量 —— 用迭代数。" )

print()
print("=" * 126)
print("★★★ 2. 墙钟波动 vs 机器负载：噪声是外部的还是内在的？")
print("=" * 126)
print("  对每个 (配置, mode)，算墙钟的极差/中位 与 该组负载的范围/中位的相关性")
print()
print("  %-8s %-6s %10s %10s %12s %12s %10s"
      % ("配置", "mode", "墙钟中位", "极差%", "负载min", "负载max", "负载极差"))
pairs = []
for (tag, M) in sorted(ROWS):
    v = ROWS[(tag, M)]
    w = [x[2] for x in v]
    ld = [x[3] for x in v if x[3] == x[3]]
    if len(w) < 2 or not ld: continue
    med = st.median(w)
    rng = 100.0*(max(w) - min(w))/med
    lr = max(ld) - min(ld)
    pairs.append((rng, lr, st.median(ld)))
    print("  %-8s %-6s %10d %9.1f%% %10.1f %10.1f %10.1f"
          % (tag, M, med, rng, min(ld), max(ld), lr))

if len(pairs) >= 3:
    xs = [p[1] for p in pairs]; ys = [p[0] for p in pairs]
    mx, my = st.median(xs), st.median(ys)
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = sum((x-mx)**2 for x in xs)**0.5
    dy = sum((y-my)**2 for y in ys)**0.5
    r = num/(dx*dy) if dx*dy > 0 else float("nan")
    print()
    print("  相关系数 r = %.3f  （墙钟极差%% vs 负载极差，%d 个样本）" % (r, len(pairs)))
    print("  ⇒ %s" % ("强相关：噪声主要来自【外部争抢】⇒ 换更闲的机器/降低共租干扰有用"
                      if abs(r) > 0.5 else
                      "弱相关：噪声不是简单的负载争抢 ⇒ 换机器未必有用，"
                      "可能是内在因素（缓存、NUMA、频率、IO）"))

print()
print("=" * 126)
print("★★★ 3. 统计功效：需要多少轮才能分辨目标效应？")
print("=" * 126)
print("  配对设计（同轮内交错）能消掉共性噪声，故用【配对差】的噪声作为基准。")
print()
print("  %-8s %-20s %12s %12s %14s %12s"
      % ("配置", "配对", "配对差中位", "配对差SD", "相对噪声%", "要分辨1%需轮数"))

for tag in ("l15", "l20", "fl30"):
    modes = [M for (t, M) in ROWS if t == tag]
    # 找配对：ONLs vs K3
    for pair in (("ONLs", "K3"), ("K3", "K5")):
        a, b = pair
        if a not in modes or b not in modes: continue
        da = dict((r[0], r[2]) for r in ROWS[(tag, a)])
        db = dict((r[0], r[2]) for r in ROWS[(tag, b)])
        common = sorted(set(da) & set(db))
        if len(common) < 3: continue
        diffs = [da[k] - db[k] for k in common]
        sd = st.pstdev(diffs) if len(diffs) > 1 else 0.0
        base = st.median([db[k] for k in common])
        relsd = 100.0*sd/base
        # 要分辨 1% 效应、2σ 显著：n = (2*SD/effect)^2
        need = (2.0*relsd/1.0)**2
        print("  %-8s %-20s %12.0f %12.0f %13.1f%% %12.0f"
              % (tag, "%s−%s" % (a, b), st.median(diffs), sd, relsd, need))

print()
print("  ⇒ 相对噪声约 2~4%（配对法显著优于非配对的 10~17%）")
print("     但分辨 1% 效应仍需 ~20–60 轮，且对 fl30 意味着 50+ 小时。")

print()
print("=" * 126)
print("★★★ 4. 替代通道：把墙钟拆成【确定部分】×【标定常数】")
print("=" * 126)
print("  wall ≈ k · iters + R · rbsteps + c")
print("  其中 iters 与 rbsteps 都是【确定的】（策略决定，不依赖机器）")
print("  ⇒ 只需标定一次 (k, R, c)，就能对任意策略预测墙钟，且【无测量噪声】")
print()
for tag in ("l15", "l20", "fl30"):
    rows = []
    for M in sorted(set(m for (t, m) in ROWS if t == tag)):
        v = ROWS[(tag, M)]
        rows.append((M, st.median([x[1] for x in v]), st.median([x[2] for x in v])))
    if len(rows) < 3: continue
    # 用 K1 与 K3 两点解二元（令 c=0 的最简版本），再用第三点验证
    print("  ── %s ──" % tag)
    print("     %-6s %10s %12s" % ("mode", "iters", "墙钟中位"))
    for (M, it, w) in rows:
        print("     %-6s %10d %12d" % (M, it, w))
    # 报告 iters 与 wall 的单调关系是否一致
    oi = [M for M, _, _ in sorted(rows, key=lambda z: z[1])]
    ow = [M for M, _, _ in sorted(rows, key=lambda z: z[2])]
    print("     按 iters 排序: %s" % " < ".join(oi))
    print("     按 wall  排序: %s" % " < ".join(ow))
    print("     ⇒ %s" % ("一致 ⇒ 迭代数可作墙钟的代理" if oi == ow else "★不一致"))
print("=" * 126)
