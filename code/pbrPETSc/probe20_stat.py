#!/usr/bin/env python3
"""levels=20 探针统计：r、tPCSetup、tIter，与 L15 对照。"""
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

rows = []
for ln in open("/root/autodl-tmp/PBR/probe20.csv"):
    p = ln.rstrip("\n").split(",")
    if len(p) != 25:
        continue
    d = {}
    try:
        for k, v in zip(CSV_HDR, p):
            d[k] = v if k in ("field", "kind") else float(v)
    except ValueError:
        continue
    rows.append(d)

print("=" * 92)
print("levels=20 探针统计")
print("=" * 92)
print("  行数 = %d   nBuildPC = %d" % (len(rows), int(rows[-1]["nBuildPC"])))
su = sum(d["tPCSetup"] for d in rows)
print("  ΣtPCSetup = %.3f s   tSetupAll = %.3f s  一致=%s"
      % (su, rows[-1]["tSetupAll"],
         "YES" if abs(su / rows[-1]["tSetupAll"] - 1) < 0.01 else "NO"))

reb = [d for d in rows if d["reused"] == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0]
rs = [d["r"] for d in reb if d["r"] > 0]
tis = [d["tIter"] for d in reb]
tss = [d["tPCSetup"] for d in reb]
print("\n  ★ 重建步数 = %d" % len(reb))
print("    r 中位        = %.2f" % st.median(rs))
print("    r 四分位      = %.2f / %.2f" % (st.quantiles(rs, n=4)[0], st.quantiles(rs, n=4)[2]))
print("    tPCSetup 中位 = %.1f us" % (st.median(tss) * 1e6))
print("    tIter 中位    = %.2f us" % (st.median(tis) * 1e6))

# 去掉前 3 个重建步（冷启动）
reb2 = reb[3:]
rs2 = [d["r"] for d in reb2 if d["r"] > 0]
print("\n  ★ 去掉前 3 个重建步后（冷启动剔除）")
print("    r 中位 = %.2f   样本 = %d" % (st.median(rs2), len(rs2)))

print("\n  ── 跨 levels 汇总（修正后）──")
print("  %7s %9s %14s %11s %13s %11s" %
      ("levels", "r", "tPCSetup/us", "tIter/us", "构造成本/ms", "r每级增量"))
L = [(0, 9.84, 448.7, 45.51), (2, 22.43, 1259.1, 56.20),
     (5, 35.00, 2920.1, 90.57), (10, 58.06, 8516.2, 146.31),
     (15, 78.02, 15287.8, 195.61),
     (20, st.median(rs2), st.median([d["tPCSetup"] for d in reb2]) * 1e6,
      st.median([d["tIter"] for d in reb2]) * 1e6)]
prev = None
for lv, r_, ts_, ti_ in L:
    inc = "" if prev is None else "%+.2f" % ((r_ - prev[1]) / (lv - prev[0]))
    print("  %7d %9.2f %14.1f %11.2f %13.3f %11s" % (lv, r_, ts_, ti_, ts_ / 1e3, inc))
    prev = (lv, r_)
print("""
  ★ 若每级增量仍稳定在 +4 附近，则 r 的上升趋势在 levels=20 依然成立。
""")
