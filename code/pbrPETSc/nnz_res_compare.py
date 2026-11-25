#!/usr/bin/env python3
"""跨分辨率对比：r 的增速衰减点是否随网格加密而后移。"""
BASE = {0:11132,1:15462,2:19674,3:27812,5:43336,8:64896,10:77906,
        12:89788,15:105426,18:118346,20:125494,25:140212,30:151802}
FINE = {5:181988,8:279342,10:341826,12:402356,15:489106,18:570906,
        20:622636,25:741916,30:846446}
NB, NF = 2268, 9072

def perlevel(tbl):
    ks = sorted(tbl)
    out = {}
    for i in range(1, len(ks)):
        dl = ks[i] - ks[i-1]
        out[(ks[i-1], ks[i])] = (tbl[ks[i]] - tbl[ks[i-1]]) / dl
    return out

pb, pf = perlevel(BASE), perlevel(FINE)

print("=" * 100)
print("跨分辨率对比：每级新增非零元 d(nnz)/d(level)")
print("=" * 100)
print("  base: 2268 单元 (n^2 = 5,143,824)   fine: 9072 单元 (n^2 = 82,301,184)")
print()
print("  %12s %14s %14s %10s" % ("levels 区间", "base/每级", "fine/每级", "比值"))
allk = sorted(set(list(pb) + list(pf)), key=lambda t: t[1])
for k in allk:
    b = pb.get(k)
    f = pf.get(k)
    bs = "%10.0f" % b if b else "%10s" % "-"
    fs = "%10.0f" % f if f else "%10s" % "-"
    rs = "%9.2f" % (f / b) if (b and f) else "%9s" % "-"
    print("  %12s %14s %14s %10s" % ("%d->%d" % k, bs, fs, rs))

print()
print("  ── 峰值位置（每级增量最大处）──")
kb = max(pb, key=lambda k: pb[k])
kf = max(pf, key=lambda k: pf[k])
print("  base 峰值区间: %d -> %d   增量 %.0f" % (kb[0], kb[1], pb[kb]))
print("  fine 峰值区间: %d -> %d   增量 %.0f" % (kf[0], kf[1], pf[kf]))
print("  ⇒ 峰值%s" % ("后移 ✓" if kf[0] > kb[0] else "未后移 ✗"))

print()
print("  ── 衰减判定：增量跌破峰值一半的位置 ──")
for nm, p, peak in (("base", pb, pb[kb]), ("fine", pf, pf[kf])):
    half = [k for k in sorted(p, key=lambda x: x[1]) if p[k] < peak / 2]
    print("  %-5s 峰值 %.0f，半数阈值 %.0f，首次跌破于 %s"
          % (nm, peak, peak/2,
             ("%d->%d (%.0f)" % (half[0][0], half[0][1], p[half[0]])) if half else "未跌破"))

print()
print("  ── 填充率对比（相对各自稠密上界）──")
print("  %8s %14s %14s %10s" % ("levels", "base 填充率", "fine 填充率", "比值"))
for lv in (5, 8, 10, 12, 15, 18, 20, 25, 30):
    if lv in BASE and lv in FINE:
        rb = BASE[lv] / (NB * NB) * 100
        rf = FINE[lv] / (NF * NF) * 100
        print("  %8d %13.3f%% %13.3f%% %10.2f" % (lv, rb, rf, rf / rb))
