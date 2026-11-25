#!/usr/bin/env python3
"""
★★★ 修正口径后的最终分析（25 列 CSV，每步 3 行）

═══════════════════════════════════════════════════════════════════════
口径修正
═══════════════════════════════════════════════════════════════════════
旧（错误）：report() 的去重闸门挡住了 CSV 写入 ⇒ ΣtPCSetup 只覆盖
            每步首次求解 ⇒ 少算 2/3（K=1: 2.458 s vs 真实 7.371/8.153 s）
新（正确）：每次求解都写一行 ⇒ ΣtPCSetup 是真实总量

25 列 CSV 的列义：
  1 timeIndex  2 field   3 kind   4 levels  5 nCells  6 nFaces  7 rep
  8 freezeAt   9 reused 10 period 11 reusedFrom 12 adopted
 13 tFreeze   14 tConvert 15 tPCSetup 16 tAssemble 17 ma 18 mp 19 tIter
 20 r         21 rTotal  22 tApplyAccum 23 nApplyCalls 24 tSetupAll 25 nBuildPC

  rep = -1   : 普通行（每次求解一行）
  rep = reps : 该步首次求解，额外带 ma/mp/tIter/r
  ⇒ 计算 r 时只应使用 rep != -1 的行
  ⇒ 计算 ΣtPCSetup 时应使用全部行
"""
import os
import re
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)")


def load_csv(path):
    rows = []
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
        rows.append(d)
    return rows


def parse_log(path):
    steps, cur = [], None
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur is not None:
                steps.append(cur)
            cur = dict(solves=[])
            continue
        if cur is None:
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur["solves"].append(int(ms.group(1)))
    if cur is not None:
        steps.append(cur)
    return steps


# 墙钟
wall = defaultdict(list)
for ln in open("fx.out"):
    m = WL.search(ln)
    if m:
        wall[int(m.group(2))].append(dict(rnd=int(m.group(1)),
                                          exe=float(m.group(4)),
                                          solve=float(m.group(5))))


def run_stats(K, rep):
    csvp = f"fx_pc_k{K}_r{rep}.csv"
    logp = f"fixed/log.r{rep}k{K}"
    if not (os.path.exists(csvp) and os.path.exists(logp)):
        return None
    rows = load_csv(csvp)
    if not rows:
        return None
    steps = parse_log(logp)
    sN = sum(sum(s["solves"]) for s in steps)

    # ★ Σ 应使用【全部行】
    setup = sum(d["tPCSetup"] for d in rows)
    asm = sum(d["tAssemble"] for d in rows)
    conv = sum(d["tConvert"] for d in rows)
    frz = sum(d["tFreeze"] for d in rows)
    nreb = sum(1 for d in rows if d["reused"] == 0)
    nsolve = len(rows)

    # ★ r 只用 rep != -1 的行
    rs = [d["r"] for d in rows if d["rep"] > 0 and d["r"] > 0]
    tis = [d["tIter"] for d in rows if d["rep"] > 0 and d["tIter"] > 0]

    pre = setup + asm + conv + frz
    return dict(setup=setup, asm=asm, conv=conv, frz=frz, pre=pre,
                nreb=nreb, nsolve=nsolve, sN=sN,
                r=st.median(rs) if rs else float("nan"),
                tIter=st.median(tis) if tis else float("nan"))


print("=" * 104)
print("★★★ 修正口径后的最终分析（levels=10，5 轮 × K∈{1,2,3,5,8}）")
print("=" * 104)

print(f"\n  1. ★★ 口径修正的验证（nBuildPC 应与行数一致）")
print(f"  {'K':>3} {'轮':>3} {'CSV行数':>8} {'nBuildPC':>9} {'ΣtPCSetup/s':>13} "
      f"{'tSetupAll/s':>12} {'一致性':>8}")
for K in sorted(wall):
    for w in wall[K]:
        S = run_stats(K, w["rnd"])
        if not S:
            continue
        rows = load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv")
        ta = rows[-1]["tSetupAll"] if rows else float("nan")
        nb = rows[-1]["nBuildPC"] if rows else 0
        ok = "✓" if abs(S["setup"] / ta - 1) < 0.01 else "✗"
        print(f"  {K:>3} {w['rnd']:>3} {S['nsolve']:>8} {int(nb):>9} "
              f"{S['setup']:>13.3f} {ta:>12.3f} {ok:>8}")

print(f"\n{'='*104}")
print("2. ★★★ 完整预算（按 K 汇总，5 轮中位）")
print(f"{'='*104}")
print(f"  {'K':>3} {'墙钟/s':>9} {'CG总/s':>9} {'分解/s':>9} {'装配/s':>8} "
      f"{'转换/s':>8} {'快照/s':>8} {'apply累计/s':>11} {'CG其余/s':>10}")
agg = defaultdict(list)
for K in sorted(wall):
    for w in wall[K]:
        S = run_stats(K, w["rnd"])
        if not S:
            continue
        # CG 其余 = CG总 − 预条件子(非apply) − apply
        rows = load_csv(f"fx_pc_k{K}_r{w['rnd']}.csv")
        ap = rows[-1]["tApplyAccum"] if rows else 0.0
        cgrest = w["solve"] - S["pre"] - ap
        agg[K].append(dict(**S, exe=w["exe"], solve=w["solve"],
                           ap=ap, cgrest=cgrest))

med = {}
for K in sorted(agg):
    m = {k: st.median([x[k] for x in agg[K]]) for k in agg[K][0]}
    med[K] = m
    print(f"  {K:>3} {m['exe']:>9.2f} {m['solve']:>9.3f} {m['setup']:>9.3f} "
          f"{m['asm']:>8.3f} {m['conv']:>8.3f} {m['frz']:>8.3f} "
          f"{m['ap']:>11.3f} {m['cgrest']:>10.3f}")

print(f"\n{'='*104}")
print("3. ★★★ 占比分解（修正后）")
print(f"{'='*104}")
print(f"  {'K':>3} {'墙钟/s':>9} {'CG占比':>8} {'预条件子占比':>13} {'分解占比':>10} "
      f"{'apply占比':>10} {'CG其余占比':>11} {'其他物理':>9}")
for K in sorted(med):
    m = med[K]
    print(f"  {K:>3} {m['exe']:>9.2f} {m['solve']/m['exe']*100:>7.1f}% "
          f"{m['pre']/m['exe']*100:>12.1f}% {m['setup']/m['exe']*100:>9.1f}% "
          f"{m['ap']/m['exe']*100:>9.1f}% {m['cgrest']/m['exe']*100:>10.1f}% "
          f"{(m['exe']-m['solve'])/m['exe']*100:>8.1f}%")

print(f"\n{'='*104}")
print("4. ★★ 收益（5 轮，5 个 K）")
print(f"{'='*104}")
base = med[1]
print(f"  {'K':>3} {'墙钟/s':>9} {'相对K=1':>10} {'CG总/s':>9} {'相对K=1':>10} "
      f"{'预条件子/s':>11} {'相对K=1':>10} {'重建数':>7}")
for K in sorted(med):
    m = med[K]
    print(f"  {K:>3} {m['exe']:>9.2f} {(m['exe']/base['exe']-1)*100:>9.2f}% "
          f"{m['solve']:>9.3f} {(m['solve']/base['solve']-1)*100:>9.2f}% "
          f"{m['pre']:>11.3f} {(m['pre']/base['pre']-1)*100:>9.2f}% "
          f"{m['nreb']:>7.0f}")

bk = min(med, key=lambda K: med[K]["exe"])
print(f"\n  ⇒ 墙钟最优 K = {bk}，收益 {(med[bk]['exe']/base['exe']-1)*100:+.2f}%")
print(f"  ⇒ CG 口径最优 K = {min(med, key=lambda K: med[K]['solve'])}")
print(f"  ⇒ 预条件子口径最优 K = {min(med, key=lambda K: med[K]['pre'])}")

print(f"\n{'='*104}")
print("5. ★ 逐轮配对检验（交错协议的核心价值）")
print(f"{'='*104}")
print(f"  {'轮':>3} {'K=1':>8} {'K=2':>8} {'K=3':>8} {'K=5':>8} {'K=8':>8} "
      f"{'K3 vs K1':>10} {'K2 vs K1':>10}")
ks = sorted(wall)
byround = defaultdict(dict)
for K in ks:
    for w in wall[K]:
        byround[w["rnd"]][K] = w["exe"]
w1 = w2 = 0
for r in sorted(byround):
    d = byround[r]
    if len(d) < len(ks):
        continue
    d3 = (d[3] / d[1] - 1) * 100
    d2 = (d[2] / d[1] - 1) * 100
    w1 += (d[3] < d[1])
    w2 += (d[2] < d[1])
    print(f"  {r:>3} {d[1]:>8.2f} {d[2]:>8.2f} {d[3]:>8.2f} {d[5]:>8.2f} "
          f"{d[8]:>8.2f} {d3:>9.2f}% {d2:>9.2f}%")
n = len([r for r in byround if len(byround[r]) == len(ks)])
print(f"\n  ⇒ K=3 优于 K=1：{w1}/{n} 轮")
print(f"  ⇒ K=2 优于 K=1：{w2}/{n} 轮")

print(f"\n{'='*104}")
print("6. ★ r 与 tIter 在修正口径下的值（未变，比值应稳定）")
print(f"{'='*104}")
print(f"  {'K':>3} {'r 中位':>9} {'tIter/µs':>10} {'tPCSetup/µs':>12}")
for K in sorted(med):
    m = med[K]
    print(f"  {K:>3} {m['r']:>9.2f} {m['tIter']*1e6:>10.2f} "
          f"{m['setup']/m['nreb']*1e6:>12.1f}")
