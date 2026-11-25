#!/usr/bin/env python3
"""
量化「盲选固定 K≠1 的风险」—— 用户所述两难的第一半（修正口径版）。

★ 前一版把 K=1 也算进盲选候选集，于是"最坏损失"永远落在 K=1 上，没有信息量。
   本版严格按命题的口径：
     · 盲选候选 = K ∈ {2,3,4,5,6}（即"离线用固定周期 K≠1"）
     · 参照 = K=1（每步重建，最保守、无需任何信息）
     · 并报告相对【最优固定 K*】的损失

三个数：
   R1  盲选 K≠1 的最坏损失（相对 K=1）—— 正 = 比每步重建还差 ⇒ 真正的"适得其反"
   R2  盲选 K≠1 的最坏损失（相对 K*）—— 说明选错的代价
   R3  有多少个配置存在"比 K=1 还差"的 K
"""
import sys, statistics as st
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import CFG, load_phase, Env, sim_fixed

TAGS = ["fx", "l15", "l20", "fine", "x3", "fl30", "sth"]
BLIND = (2, 3, 4, 5, 6)

print("=" * 126)
print("★★★ 盲选固定 K≠1 的风险（无算例信息时的后果）")
print("=" * 126)
print("  %-6s %-12s %-16s %-16s %-18s %s"
      % ("配置", "K* 位置", "R1 最坏vs K=1", "R2 最坏vs K*", "R1 出现在哪个K", "比K=1差的K"))

n_bad = 0
globR1 = -1e9
globR2 = -1e9
for tag in TAGS:
    d = load_phase(tag)
    if not d:
        continue
    env = Env(d["tab"], sFact=d["s"])
    lvl, T, B0 = CFG[tag]
    lo, hi = d["r1"], d["r1"] * d["s"]

    kstars = set()
    r1w = -1e9; r1k = None
    r2w = -1e9
    bad = set()
    for i in range(13):
        rho = lo + (hi - lo) * i / 12.0
        c = {k: sim_fixed(env, rho, k, T, B0)[0] for k in (1,) + BLIND
             if k <= env.amax_data + 1}
        c1 = c[1]
        bk = min(c, key=c.get); kstars.add(bk)
        best = c[bk]
        for k in BLIND:
            if k not in c:
                continue
            v = 100.0 * (c[k] - c1) / c1          # 相对 K=1
            if v > r1w:
                r1w, r1k = v, k
            if v > 0:
                bad.add(k)
            v2 = 100.0 * (c[k] - best) / best      # 相对 K*
            r2w = max(r2w, v2)
    globR1 = max(globR1, r1w)
    globR2 = max(globR2, r2w)
    if bad:
        n_bad += 1
    print("  %-6s %-12s %+15.2f%% %+15.2f%% K=%-16d %s"
          % (tag, "{%s}" % ",".join("K%d" % k for k in sorted(kstars)),
             r1w, r2w, r1k,
             "{%s}" % ",".join("K%d" % k for k in sorted(bad)) if bad else "无"))

print("\n  ⇒ R1 全配置最坏 = %+.2f%%（相对每步重建）" % globR1)
print("  ⇒ R2 全配置最坏 = %+.2f%%（相对事后最优固定周期）" % globR2)
print("  ⇒ 存在「比 K=1 还差」的 K 的配置：%d/7" % n_bad)
print()
print("  ★ 判读：")
print("     R1 > 0 意味着一件事：**离线盲选 K≠1 有可能比「不做任何决策」（每步重建）还差**。")
print("     这就是用户所述的「适得其反」——而它只需一行代码即可避免（默认 K=1），")
print("     但要获得 K* 的收益就必须付出扫描代价。这正是两难。")
