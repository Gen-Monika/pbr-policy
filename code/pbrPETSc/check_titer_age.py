#!/usr/bin/env python3
"""
★ 检验假设：陈旧的预条件子是否让【每次迭代】也变慢？

═══════════════════════════════════════════════════════════════════════
动机
═══════════════════════════════════════════════════════════════════════
同源实验显示：内部模型（W = Σsetup + Σasm + Σconv + ΣN·tIter）
在高 K 下严重低估代价（K=8 时低估达 51.86 个百分点）。

若 tIter 随年龄增长（陈旧因子令 apply 变慢），则模型会低估。

重要：report() 在每个时间步都被调用（包括复用步），
      所以 CSV 里【本来就有】复用步的 ma/mp/tIter。
      本脚本直接把两者分开统计。
"""
import os
import re
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal").split(",")


def load_csv(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 21:
            continue
        d = {}
        try:
            for k, v in zip(CSV_HDR, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


print("=" * 100)
print("★ 重建步 vs 复用步：tIter / ma / mp 的对比")
print("=" * 100)

print(f"\n  {'K':>3} {'轮':>3} {'类别':>6} {'样本':>6} {'ma/µs':>9} {'mp/µs':>9} "
      f"{'tIter/µs':>10} {'相对重建步':>11}")

summary = defaultdict(dict)
for K in (1, 2, 3, 5, 8):
    for R in (1, 2, 3):
        path = f"ss_k{K}_r{R}.csv"
        if not os.path.exists(path):
            continue
        rows = load_csv(path)
        if not rows:
            continue
        reb = [d for d in rows if d["reused"] == 0]
        reu = [d for d in rows if d["reused"] == 1]
        for tag, grp in (("rebuild", reb), ("reuse", reu)):
            if not grp:
                continue
            ma = st.median([d["ma"] for d in grp])
            mp = st.median([d["mp"] for d in grp])
            ti = st.median([d["tIter"] for d in grp])
            ref = st.median([d["tIter"] for d in reb]) if reb else None
            rel = f"{(ti/ref-1)*100:+10.2f}%" if ref else ""
            summary[K].setdefault(tag, []).append(ti)
            if R == 1 or tag == "reuse":
                print(f"  {K:>3} {R:>3} {tag:>6} {len(grp):>6} {ma*1e6:>9.2f} "
                      f"{mp*1e6:>9.2f} {ti*1e6:>10.2f} {rel:>11}")

print(f"\n{'='*100}")
print("★ 按 K 汇总（三次重复的中位）")
print(f"{'='*100}")
print(f"  {'K':>3} {'重建步 tIter/µs':>16} {'复用步 tIter/µs':>16} "
      f"{'复用/重建':>11} {'含义':>24}")
for K in sorted(summary):
    rb = summary[K].get("rebuild", [])
    ru = summary[K].get("reuse", [])
    if not rb:
        continue
    tr = st.median(rb)
    if ru:
        tu = st.median(ru)
        ratio = tu / tr
        note = ("复用更贵" if ratio > 1.02
                else ("复用更便宜" if ratio < 0.98 else "无明显差异"))
        print(f"  {K:>3} {tr*1e6:>16.2f} {tu*1e6:>16.2f} {ratio:>11.3f} {note:>24}")
    else:
        print(f"  {K:>3} {tr*1e6:>16.2f} {'(无复用步)':>16} {'—':>11} {'—':>24}")

print(f"\n{'='*100}")
print("★ 年龄分辨：tIter 是否随【预条件子年龄】增长？")
print(f"{'='*100}")
for K in (3, 8):
    bya = defaultdict(list)
    for R in (1, 2, 3):
        path = f"ss_k{K}_r{R}.csv"
        if not os.path.exists(path):
            continue
        for d in load_csv(path):
            if d["tIter"] <= 0:
                continue
            age = int(d["timeIndex"] - (d["reusedFrom"] if d["reused"] == 1
                                        else d["timeIndex"]))
            bya[age].append(d["tIter"])
    if bya:
        print(f"\n  ── K={K} ──")
        print(f"  {'age':>4} {'样本':>6} {'tIter 中位/µs':>14}")
        for a in sorted(bya)[:10]:
            print(f"  {a:>4} {len(bya[a]):>6} {st.median(bya[a])*1e6:>14.2f}")

print(f"""
{'='*100}
★ 结论
{'='*100}
  若"复用步 tIter 明显高于重建步"，则内部模型低估陈旧代价的原因即被确证。
  若两者接近，则该假设被否证，需另找原因。
""")
