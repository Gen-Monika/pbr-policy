#!/usr/bin/env python3
"""levels=15 探针统计 + 追查 r=-1。"""
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")

rows = []
for ln in open("probe15.csv"):
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

print("=" * 88)
print("levels=15 探针统计")
print("=" * 88)
print(f"\n  行数 = {len(rows)}")

# r=-1 的分布
neg = [d for d in rows if d["r"] < 0]
print(f"\n  r < 0 的行数 = {len(neg)}")
for d in neg[:10]:
    print(f"    t={int(d['timeIndex'])} rep={int(d['rep'])} reused={int(d['reused'])} "
          f"tPCSetup={d['tPCSetup']*1e6:.1f}µs ma={d['ma']} mp={d['mp']} "
          f"tIter={d['tIter']} r={d['r']:.2f}")

# rep 分布
rp = defaultdict(int)
for d in rows:
    rp[int(d["rep"])] += 1
print(f"\n  rep 分布: {dict(rp)}")

# 只在重建步统计
reb = [d for d in rows if d["reused"] == 0 and d["tPCSetup"] > 1e-4]
rs = [d["r"] for d in reb if d["r"] > 0]
tis = [d["tIter"] for d in reb if d["tIter"] > 0]
tss = [d["tPCSetup"] for d in reb]
print(f"\n  ★ 重建步数 = {len(reb)}")
print(f"    r 中位      = {st.median(rs):.2f}")
print(f"    tPCSetup 中位 = {st.median(tss)*1e6:.1f} µs")
print(f"    tIter 中位    = {st.median(tis)*1e6:.2f} µs")

# 汇总列
print(f"\n  tSetupAll = {rows[-1]['tSetupAll']:.3f} s")
print(f"  nBuildPC  = {int(rows[-1]['nBuildPC'])}")
print(f"  ΣtPCSetup = {sum(d['tPCSetup'] for d in rows):.3f} s")
print(f"  applyAccum= {rows[-1]['tApplyAccum']:.3f} s")
print(f"  nApplyCalls = {int(rows[-1]['nApplyCalls'])}")

print(f"\n  {'levels':>7} {'r':>8} {'tPCSetup/µs':>13} {'tIter/µs':>10} {'构造成本/ms':>12}")
for lv, r_, ts_, ti_ in ((0, 9.84, 448.7, 45.51), (2, 22.43, 1259.1, 56.20),
                         (5, 35.00, 2920.1, 90.57), (10, 58.06, 8516.2, 146.31),
                         (15, st.median(rs), st.median(tss)*1e6, st.median(tis)*1e6)):
    print(f"  {lv:>7} {r_:>8.2f} {ts_:>13.1f} {ti_:>10.2f} {ts_/1e3:>12.3f}")
