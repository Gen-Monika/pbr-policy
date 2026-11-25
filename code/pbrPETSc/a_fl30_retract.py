#!/usr/bin/env python3
"""
★★★ a_fl30_retract.py —— fl30 "在线优于所有固定周期" 主张的撤回计算

★ 撤回理由（两条,任一条即足以撤回）：
  R1  基准选错：原文档称"最优固定周期 = K5(252614ms)"，但 K3(248792ms) 更快。
      以 K5 为基准算出的 −1.08% 是【与次优比较】，不是与最优比较。
  R2  即便基准正确，逐轮方向不一致（−0.68% / +0.44% / −5.59%），
      且组内极差 4.4–9.8%，1% 量级的效应不可分辨（与第二层的 K* 不可辨识同源）。

本脚本只读 a2B.log 的原始三轮墙钟（已落盘于文档），做纯算术复核，不接触服务器。
"""
import statistics as st

# a2B.log 原始三轮墙钟（ms）—— 与 docs/a2b_fl30_decision 第 1 节表一致
W = {
    "K1":   [473896, 463758, 485404],
    "K3":   [242733, 248792, 267071],
    "K5":   [254614, 251082, 252614],
    "ONLs": [241074, 249894, 252136],
    "ONLp": [251357, 250120, 245034],
}
# 迭代数与重建步数（跨轮逐位相同，与墙钟无关的机器无关量）
ITRB = {"K1": (11953, 720), "K3": (26373, 306), "K5": (52114, 224),
        "ONLs": (26648, 305), "ONLp": (37696, 254)}
POL = ("ONLs", "ONLp")


def med(k): return st.median(W[k])
def spread(k): return 100.0 * (max(W[k]) - min(W[k])) / med(k)
def pair(a, b):
    """a 相对 b 的中位差、逐轮胜负、各轮差。"""
    wins = sum(1 for i in range(3) if W[a][i] < W[b][i])
    losses = sum(1 for i in range(3) if W[a][i] > W[b][i])
    md = 100.0 * (med(a) - med(b)) / med(b)
    ds = [100.0 * (W[a][i] - W[b][i]) / W[b][i] for i in range(3)]
    return md, wins, losses, ds


print("=" * 100)
print("★★★ fl30 撤回计算：R1 基准是否选错")
print("=" * 100)
print()
print("  %-6s %12s %12s %12s" % ("组", "中位ms", "相对K3", "组内极差"))
for k in ("K1", "K3", "K5", "ONLs", "ONLp"):
    d = 100.0 * (med(k) - med("K3")) / med("K3")
    print("  %-6s %12.0f %11.2f%% %11.1f%%" % (k, med(k), d, spread(k)))
print()
fixed = {"K1": med("K1"), "K3": med("K3"), "K5": med("K5")}
best = min(fixed, key=fixed.get)
print("  三个固定周期的中位：K1=%.0f  K3=%.0f  K5=%.0f" % (fixed["K1"], fixed["K3"], fixed["K5"]))
print("  ⇒ 真正的最优固定周期 = %s" % best)
print("  ⇒ 原文档用的是 K5 —— 基准错了（K5 是次优，比 %s 慢 %.2f%%）"
      % (best, 100.0 * (fixed["K5"] - fixed[best]) / fixed[best]))

print()
print("=" * 100)
print("★★★ R2 逐轮方向是否一致")
print("=" * 100)
print()
print("  %-14s %10s %8s %8s %s" % ("比较", "中位差%", "逐轮胜", "逐轮负", "各轮差%"))
for a, b in ((POL[0], best), (POL[1], best), ("K5", best), (POL[0], "K5"), (POL[1], "K5")):
    md, w, l, ds = pair(a, b)
    print("  %-14s %+10.2f %8d %8d  %s"
          % ("%s vs %s" % (a, b), md, w, l, "  ".join("%+.2f" % d for d in ds)))

print()
print("=" * 100)
print("★★★ 撤回后的正确表述")
print("=" * 100)
print()
md, w, l, ds = pair("ONLs", best)
print("  在线策略（ONLs）vs 最优固定周期（%s）：" % best)
print("     中位差 %+.2f%%（在线略慢）" % md)
print("     逐轮 %d 胜 %d 负，各轮 %s" % (w, l, "  ".join("%+.2f%%" % d for d in ds)))
print("     在线组内极差 %.1f%%，基准组内极差 %.1f%%" % (spread("ONLs"), spread(best)))
print()
print("  逐轮方向不一致 + 中位差为正 ⇒ 【在线优于所有固定周期】不成立。")
print("  正确表述：在线策略与最优固定周期在墙钟上不可分辨；")
print("            两者都显著优于每步重建（K=1）。")
print()
print("  保留的部分（方向极强，不受此撤回影响）：")
for k in ("K3", "K5", "ONLs", "ONLp"):
    d = 100.0 * (med(k) - med("K1")) / med("K1")
    print("     %-5s 相对 K=1：%.1f%%（%d 步重建 vs 720）" % (k, d, ITRB[k][1]))

print()
print("=" * 100)
print("★★★ 附：机器无关量（不依赖墙钟，故不受撤回影响）")
print("=" * 100)
print()
print("  %-6s %10s %10s" % ("组", "Σ迭代数", "重建步数"))
for k, (it, rb) in ITRB.items():
    print("  %-6s %10d %10d" % (k, it, rb))
print()
print("  注：若用机器无关指标，近邻 K 之间的 cost 差异仍会随 ρ 变号")
print("      （见 layer2 文档：最优 K 在 ρ 的不同取值下从 K3 移到 K4/K5），")
print("      故 fl30 同样【不】支持「某个 K 绝对最优」的表述。")
