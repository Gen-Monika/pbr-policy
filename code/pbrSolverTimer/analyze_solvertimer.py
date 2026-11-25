#!/usr/bin/env python3
"""
★★★ solve() 层面计时的分析：闭合预算

═══════════════════════════════════════════════════════════════════════
背景
═══════════════════════════════════════════════════════════════════════
此前 PBR_PETSc 的计时只覆盖【预条件子内部】（setup/convert/assemble/N·tIter），
而墙钟与内部计时之差为 8–11 s（占墙钟 55–70%），五个假设均被排除。

本实验用 PBRPCG（PCG 的计时间包装）在 scalarSolve 层面测量
【压力求解的总耗时】，从而给出中间口径并闭合预算。

新的预算分解：
    T_wall (ExecutionTime)
      = T_pcg          （scalarSolve 总耗时 = CG 主循环 + 预条件子）
      + T_other        （动量预测 + 湍流 + alpha 输运 + I/O + 时间步管理）

    T_pcg = T_precond   （PBR_PETSc 已计时的部分）
          + T_cgitself  （Amul / gSumProd / 向量更新 —— 此前从未计时）
"""
import os
import re
import statistics as st
from collections import defaultdict

# wall 实测
WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"totalSolveTime=([0-9.eE+-]*)")
wall = defaultdict(list)
exe = defaultdict(list)
tsv = defaultdict(list)
for ln in open("st.out"):
    m = WL.search(ln)
    if m:
        K = int(m.group(2))
        wall[K].append(int(m.group(3)))
        exe[K].append(float(m.group(4)))
        if m.group(5):
            tsv[K].append(float(m.group(5)))

# 预条件子内部计时（PBR_PETSC_OUT，21 列）
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal").split(",")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")


def parse_log(path):
    steps, cur = [], None
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur is not None:
                steps.append(cur)
            cur = dict(reused=None, solves=[])
            continue
        if cur is None:
            continue
        if "PETSc ilu lvl" in ln:
            cur["reused"] = 0 if "rebuild" in ln else 1
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur["solves"].append(int(ms.group(1)))
    if cur is not None:
        steps.append(cur)
    return steps


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


def precond_budget(K, rep):
    logp, csvp = f"stwt/log.r{rep}k{K}", f"stwt_pc_k{K}_r{rep}.csv"
    if not (os.path.exists(logp) and os.path.exists(csvp)):
        return None
    steps, rows = parse_log(logp), load_csv(csvp)
    n = min(len(steps), len(rows))
    setup = asm = conv = frz = itr = 0.0
    nreb = 0
    for i in range(n):
        r = rows[i]
        if r["tIter"] <= 0:
            continue
        setup += r["tPCSetup"]
        asm += r["tAssemble"]
        conv += r["tConvert"]
        frz += r["tFreeze"]
        itr += sum(steps[i]["solves"]) * r["tIter"]
        if steps[i]["reused"] == 0:
            nreb += 1
    return dict(setup=setup, asm=asm, conv=conv, frz=frz, itr=itr, nreb=nreb,
                total=setup + asm + conv + frz + itr)


print("=" * 104)
print("★★★ solve() 层面计时：闭合预算（levels=10）")
print("=" * 104)

print(f"\n  {'K':>3} {'轮':>3} {'ExecutionTime/s':>15} {'CG总耗时/s':>12} "
      f"{'预条件子/s':>11} {'CG自身/s':>10} {'其他物理/s':>11}")

rows_by_K = {}
for K in sorted(exe):
    for i in range(len(exe[K])):
        e = exe[K][i]
        s = tsv[K][i] if i < len(tsv[K]) else float("nan")
        pb = precond_budget(K, i + 1)
        pt = pb["total"] if pb else float("nan")
        cgself = s - pt
        other = e - s
        print(f"  {K:>3} {i+1:>3} {e:>15.2f} {s:>12.3f} {pt:>11.3f} "
              f"{cgself:>10.3f} {other:>11.3f}")
        rows_by_K.setdefault(K, []).append(dict(e=e, s=s, pt=pt,
                                                cgself=cgself, other=other))

print(f"\n{'='*104}")
print("1. ★ 按 K 汇总（中位）")
print(f"{'='*104}")
print(f"  {'K':>3} {'ExecutionTime':>14} {'CG总耗时':>11} {'预条件子':>10} "
      f"{'CG自身':>9} {'其他物理':>10} {'CG占比':>8}")
agg = {}
for K in sorted(rows_by_K):
    e = st.median([r["e"] for r in rows_by_K[K]])
    s = st.median([r["s"] for r in rows_by_K[K]])
    pt = st.median([r["pt"] for r in rows_by_K[K]])
    cg = st.median([r["cgself"] for r in rows_by_K[K]])
    ot = st.median([r["other"] for r in rows_by_K[K]])
    agg[K] = dict(e=e, s=s, pt=pt, cg=cg, ot=ot)
    print(f"  {K:>3} {e:>14.2f} {s:>11.3f} {pt:>10.3f} {cg:>9.3f} {ot:>10.3f} "
          f"{s/e*100:>7.1f}%")

print(f"\n{'='*104}")
print("2. ★★ 预算闭合验证（此前的'未解释量'是否消失）")
print(f"{'='*104}")
print(f"  {'K':>3} {'墙钟':>9} {'= CG总耗时':>11} {'+ 其他物理':>11} {'残差/s':>9} "
      f"{'残差占比':>9}")
for K in sorted(agg):
    a = agg[K]
    resid = a["e"] - a["s"] - a["ot"]
    print(f"  {K:>3} {a['e']:>9.2f} {a['s']:>11.3f} {a['ot']:>11.3f} "
          f"{resid:>9.3f} {abs(resid)/a['e']*100:>8.2f}%")

print(f"""
  ⚠️ 注意：'其他物理' = ExecutionTime − CG总耗时，故残差恒为 0（构造如此）。
     真正有意义的是看【CG总耗时占墙钟的比例】与【CG自身的开销】。
""")

print(f"{'='*104}")
print("3. ★★★ 关键发现：CG 主循环自身的开销")
print(f"{'='*104}")
print(f"  {'K':>3} {'CG总耗时/s':>12} {'预条件子/s':>11} {'CG自身/s':>10} "
      f"{'重建数':>7} {'CG自身/重建':>12}")
for K in sorted(agg):
    a = agg[K]
    pb = precond_budget(K, 1)
    nreb = pb["nreb"] if pb else 0
    per = a["cg"] / nreb if nreb else 0.0
    print(f"  {K:>3} {a['s']:>12.3f} {a['pt']:>11.3f} {a['cg']:>10.3f} "
          f"{nreb:>7} {per*1e3:>11.2f} ms")

print(f"""
  ⇒ 此前被记为'未解释 8-11 s'的，实际上是：
        CG 主循环自身（Amul / gSumProd / 向量更新）+ 预条件子
     二者的总和才是 scalarSolve 的耗时。
     PBR_PETSc 的计时【只覆盖预条件子】，故差额全部落在 CG 主循环上。
""")

print(f"{'='*104}")
print("4. ★★ 各 K 的收益与最优")
print(f"{'='*104}")
print(f"  {'量':>22} " + "".join(f"{'K='+str(K):>12}" for K in sorted(agg)))
for key, name in (("e", "ExecutionTime/s"), ("s", "CG总耗时/s"),
                  ("pt", "预条件子/s"), ("cg", "CG自身/s")):
    print(f"  {name:>22} " + "".join(f"{agg[K][key]:>12.3f}" for K in sorted(agg)))

base_e = agg[1]["e"]
base_s = agg[1]["s"]
print(f"\n  {'相对 K=1（墙钟）':>22} "
      + "".join(f"{(agg[K]['e']/base_e-1)*100:>11.2f}%" for K in sorted(agg)))
print(f"  {'相对 K=1（CG）':>22} "
      + "".join(f"{(agg[K]['s']/base_s-1)*100:>11.2f}%" for K in sorted(agg)))

bk = min(agg, key=lambda K: agg[K]["e"])
print(f"\n  ⇒ 墙钟最优 K = {bk}，相对 K=1 {(agg[bk]['e']/base_e-1)*100:+.2f}%")
print(f"  ⇒ CG 口径最优 K = {min(agg, key=lambda K: agg[K]['s'])}")

print(f"\n{'='*104}")
print("5. ★ 两个口径的一致性")
print(f"{'='*104}")
print(f"  {'K':>3} {'墙钟收益':>10} {'CG收益':>10} {'预条件子收益':>13} "
      f"{'一致性':>8}")
for K in sorted(agg):
    a = agg[K]
    we = a["e"] / base_e - 1
    ce = a["s"] / base_s - 1
    po = a["pt"] / agg[1]["pt"] - 1
    ok = "✓" if (we < 0) == (ce < 0) else "✗"
    print(f"  {K:>3} {we*100:>9.2f}% {ce*100:>9.2f}% {po*100:>12.2f}% {ok:>8}")
