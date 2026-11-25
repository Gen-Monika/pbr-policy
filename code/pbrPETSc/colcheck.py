#!/usr/bin/env python3
"""列义求解：用两个恒等式约束反推 20 列版本的真实字段顺序。"""
import collections

HDR20 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
         "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")

rows = [l.rstrip("\n").split(",") for l in open("s_k2_r1.csv")]
print(f"ncols={len(rows[0])}  nrows={len(rows)}")

bad = 0
for idx in (99, 100, 101, 105):
    r = rows[idx]
    d = dict(zip(HDR20, r))
    for k in HDR20:
        if k not in ("field", "kind"):
            d[k] = float(d[k])
    print()
    print(f"--- 行 {idx+1}  timeIndex={r[0]} ---")
    for k in HDR20:
        print(f"    {k:12s} = {d[k]}")
    ok1 = abs(d["tPCSetup"]/d["tIter"] - d["r"]) < 1e-3
    ok2 = abs((d["tConvert"]+d["tPCSetup"])/d["tIter"] - d["rTotal"]) < 1e-3
    ok3 = abs(d["ma"]+d["mp"] - d["tIter"]) < 1e-9
    print(f"    恒等式 r      : {ok1}")
    print(f"    恒等式 rTotal : {ok2}")
    print(f"    恒等式 tIter  : {ok3}")
    if not (ok1 and ok2 and ok3):
        bad += 1
print()
print(f"⇒ 该列序在抽查的 4 行中，{'全部成立 ✓' if bad == 0 else f'{bad} 行不成立 ✗'}")

# 逐列分布（帮助肉眼确认语义）
print("\n逐列取值形态（前 6 个不同值）：")
for i, name in enumerate(HDR20):
    ctr = collections.Counter(r[i] for r in rows)
    vals = list(ctr.keys())[:6]
    print(f"  [{i:2d}] {name:12s} 不同值{len(ctr):5d}  例: {vals}")
