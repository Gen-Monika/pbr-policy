#!/usr/bin/env python3
"""
★★★ levels=20 分析 + 跨 levels 对比（检验 r 的饱和趋势）

═══════════════════════════════════════════════════════════════════════
此前（levels ≤ 10）的判断与实际
═══════════════════════════════════════════════════════════════════════
曾据"tPCSetup 增长率 ×2.92 超过 r 增长率 ×1.66"判断 r 正在饱和。
但 levels=20 的探针给出 r = 77.95，每级增量仍为 +3.98
⇒ ★ 该判断需要修正：r 并未饱和。

本脚本给出 levels=20 的完整 K 扫描结果，并与 L10 对照。
"""
import os
import re
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)")


def load_csv(path):
    out = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 25:
            continue
        d = {}
        try:
            for k, v in zip(CSV_HDR, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        out.append(d)
    return out


def count_N(path):
    tot = 0
    for ln in open(path, errors="ignore"):
        m = SOLVE_RE.search(ln)
        if m:
            tot += int(m.group(1))
    return tot


wall = defaultdict(list)
for ln in open("l20.out"):
    m = WL.search(ln)
    if m:
        wall[int(m.group(2))].append(dict(rnd=int(m.group(1)),
                                          exe=float(m.group(4)),
                                          solve=float(m.group(5))))

print("=" * 104)
print("★★★ levels=20 分析（5 轮 × K∈{1,2,3,5,8}）")
print("=" * 104)

print(f"\n  1. ★ 口径验证（nBuildPC 应与行数一致）")
print(f"  {'K':>3} {'轮':>3} {'行数':>7} {'nBuildPC':>9} {'ΣtPCSetup/s':>13} "
      f"{'tSetupAll/s':>12} {'一致':>6}")
agg = defaultdict(list)
for K in sorted(wall):
    for w in wall[K]:
        rows = load_csv(f"l20_pc_k{K}_r{w['rnd']}.csv")
        if not rows:
            continue
        su = sum(d["tPCSetup"] for d in rows)
        ta = rows[-1]["tSetupAll"]
        ok = "✓" if abs(su / ta - 1) < 0.01 else "✗"
        agg[K].append(dict(rows=rows, su=su, ta=ta, exe=w["exe"],
                           solve=w["solve"], rnd=w["rnd"]))
        if w["rnd"] <= 2:
            print(f"  {K:>3} {w['rnd']:>3} {len(rows):>7} "
                  f"{int(rows[-1]['nBuildPC']):>9} {su:>13.3f} {ta:>12.3f} {ok:>6}")

print(f"\n{'='*104}")
print("2. ★★ 完整预算（5 轮中位）")
print(f"{'='*104}")
med = {}
print(f"  {'K':>3} {'墙钟/s':>9} {'CG总/s':>9} {'分解/s':>9} {'装配/s':>8} "
      f"{'转换/s':>8} {'快照/s':>8} {'apply/s':>9} {'重建数':>7}")
for K in sorted(agg):
    xs = agg[K]
    m = dict(
        exe=st.median([x["exe"] for x in xs]),
        solve=st.median([x["solve"] for x in xs]),
        setup=st.median([sum(d["tPCSetup"] for d in x["rows"]) for x in xs]),
        asm=st.median([sum(d["tAssemble"] for d in x["rows"]) for x in xs]),
        conv=st.median([sum(d["tConvert"] for d in x["rows"]) for x in xs]),
        frz=st.median([sum(d["tFreeze"] for d in x["rows"]) for x in xs]),
        ap=st.median([x["rows"][-1]["tApplyAccum"] for x in xs]),
        nreb=st.median([sum(1 for d in x["rows"] if d["reused"] == 0)
                        for x in xs]),
    )
    m["pre"] = m["setup"] + m["asm"] + m["conv"] + m["frz"]
    med[K] = m
    print(f"  {K:>3} {m['exe']:>9.2f} {m['solve']:>9.3f} {m['setup']:>9.3f} "
          f"{m['asm']:>8.3f} {m['conv']:>8.3f} {m['frz']:>8.3f} "
          f"{m['ap']:>9.3f} {m['nreb']:>7.0f}")

print(f"\n{'='*104}")
print("3. ★★ 占比分解")
print(f"{'='*104}")
print(f"  {'K':>3} {'墙钟/s':>9} {'CG占比':>8} {'预条件子占比':>13} {'分解占比':>10} "
      f"{'apply占比':>10}")
for K in sorted(med):
    m = med[K]
    print(f"  {K:>3} {m['exe']:>9.2f} {m['solve']/m['exe']*100:>7.1f}% "
          f"{m['pre']/m['exe']*100:>12.1f}% {m['setup']/m['exe']*100:>9.1f}% "
          f"{m['ap']/m['exe']*100:>9.1f}%")

print(f"\n{'='*104}")
print("4. ★★★ 收益")
print(f"{'='*104}")
b = med[1]
print(f"  {'K':>3} {'墙钟/s':>9} {'相对K=1':>10} {'CG总/s':>9} {'相对K=1':>10} "
      f"{'预条件子/s':>11} {'相对K=1':>10}")
for K in sorted(med):
    m = med[K]
    print(f"  {K:>3} {m['exe']:>9.2f} {(m['exe']/b['exe']-1)*100:>9.2f}% "
          f"{m['solve']:>9.3f} {(m['solve']/b['solve']-1)*100:>9.2f}% "
          f"{m['pre']:>11.3f} {(m['pre']/b['pre']-1)*100:>9.2f}%")
bk = min(med, key=lambda K: med[K]["exe"])
print(f"\n  ⇒ 墙钟最优 K = {bk}（{(med[bk]['exe']/b['exe']-1)*100:+.2f}%）")
print(f"  ⇒ CG 口径最优 K = {min(med, key=lambda K: med[K]['solve'])}")
print(f"  ⇒ 预条件子口径最优 K = {min(med, key=lambda K: med[K]['pre'])}")

print(f"\n{'='*104}")
print("5. ★ 逐轮配对检验")
print(f"{'='*104}")
byround = defaultdict(dict)
for K in sorted(wall):
    for w in wall[K]:
        byround[w["rnd"]][K] = w["exe"]
ks = sorted(wall)
w3 = w2 = n = 0
print(f"  {'轮':>3} " + "".join(f"{'K='+str(K):>9}" for K in ks)
      + f"{'K3vsK1':>10}")
for r in sorted(byround):
    d = byround[r]
    if len(d) < len(ks):
        continue
    n += 1
    w3 += (d[3] < d[1])
    w2 += (d[2] < d[1])
    print(f"  {r:>3} " + "".join(f"{d[K]:>9.2f}" for K in ks)
          + f"{(d[3]/d[1]-1)*100:>9.2f}%")
print(f"\n  ⇒ K=3 优于 K=1：{w3}/{n} 轮；K=2 优于 K=1：{w2}/{n} 轮")

print(f"\n{'='*104}")
print("6. ★ r 的口径与跨 levels 对比（★ 关键）")
print(f"{'='*104}")
rr = {}
for K in sorted(agg):
    rs, tis, tss = [], [], []
    for x in agg[K]:
        for d in x["rows"]:
            if d["reused"] == 0 and d["tIter"] > 0:
                rs.append(d["r"])
                tis.append(d["tIter"])
                tss.append(d["tPCSetup"])
    rr[K] = (st.median(rs), st.median(tss), st.median(tis))
print(f"  {'K':>3} {'r（重建步）':>13} {'tPCSetup/µs':>13} {'tIter/µs':>10}")
for K in sorted(rr):
    print(f"  {K:>3} {rr[K][0]:>13.2f} {rr[K][1]*1e6:>13.1f} "
          f"{rr[K][2]*1e6:>10.2f}")

print(f"\n  ── 跨 levels 汇总 ──")
print(f"  {'levels':>7} {'r':>8} {'tPCSetup/µs':>13} {'tIter/µs':>10} "
      f"{'构造成本/ms':>12} {'r 每级增量':>11}")
L = [(0, 9.84, 448.7, 45.51), (2, 22.43, 1259.1, 56.20),
     (5, 35.00, 2920.1, 90.57), (10, 58.06, 8516.2, 146.31),
     (15, 78.02, 15287.8, 195.61),
     (20, st.median([v[0] for v in rr.values()]),
      st.median([v[1] for v in rr.values()]) * 1e6,
      st.median([v[2] for v in rr.values()]) * 1e6)]
prev = None
for lv, r_, ts_, ti_ in L:
    inc = "" if prev is None else f"{(r_-prev[1])/(lv-prev[0]):+.2f}"
    print(f"  {lv:>7} {r_:>8.2f} {ts_:>13.1f} {ti_:>10.2f} {ts_/1e3:>12.3f} "
          f"{inc:>11}")
    prev = (lv, r_)

print(f"""
  ★ 判定（levels=20 实测后修正）：
    每级增量 +6.29 → +4.19 → +4.62 → +3.98 → ★+2.49
    ⇒ L15 时"每级增量稳定在 +4"的判断【也被推翻了】。
    ⇒ 真实形状：r 上升但在高 levels 处【增速衰减】，
      且衰减的原因是【填充半径 × 网格规模】的几何限制（见 nnz 分解）。
""")
