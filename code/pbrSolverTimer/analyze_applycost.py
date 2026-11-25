#!/usr/bin/env python3
"""
★★★ final：CG 每迭代成本异常的精确核算

═══════════════════════════════════════════════════════════════════════
已知（本轮实验）
═══════════════════════════════════════════════════════════════════════
  K    applyAccum/s   nApply   每次apply     CG总耗时/s   ΣN(迭代数)
  1       0.892       7938     112.4 µs      12.13       7957
  3       1.554      12496     124.3 µs       9.91      12527
  8       4.603      35386     130.1 µs      12.51      35486

★ note: nApply = ΣN + 少量（每次 solve 多一次 apply？）
   K=1: 7938 vs ΣN 7957  ⇒ nApply 略小于 ΣN
   K=3: 12496 vs 12527
   K=8: 35386 vs 35486

⇒ 每次 apply 成本【基本恒定】（112-130 µs），与孤立的 tIter（146 µs）同量级。
⇒ 因此"CG 每迭代成本随 K 下降"这一表象，必然来自
   【CG总耗时 − applyAccum − 预条件子其它部分】这一余项。

本脚本把余项算出来，看它是否随 K 变化。
"""
import os
import re
import statistics as st
from collections import defaultdict

WL = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)\s+"
                r"solveTime=([0-9.eE+-]+)\s+applyAccum=([0-9.eE+-]+)\s+nApply=(\d+)")
rows = defaultdict(list)
for ln in open("ac.out"):
    m = WL.search(ln)
    if m:
        rows[int(m.group(2))].append(dict(
            wall_ms=int(m.group(3)), exe=float(m.group(4)),
            solve=float(m.group(5)), apply=float(m.group(6)),
            napply=int(m.group(7)), rnd=int(m.group(1))))

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls").split(",")
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
    out = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 23:
            continue
        d = {}
        try:
            for k, v in zip(CSV_HDR, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        out.append(d)
    return out


def precond(K, rep):
    logp, csvp = f"applycost/log.r{rep}k{K}", f"ac_pc_k{K}_r{rep}.csv"
    if not (os.path.exists(logp) and os.path.exists(csvp)):
        return None
    steps, rowsx = parse_log(logp), load_csv(csvp)
    n = min(len(steps), len(rowsx))
    setup = asm = conv = frz = 0.0
    nreb = 0
    sN = 0
    for i in range(n):
        r = rowsx[i]
        if r["tIter"] <= 0:
            continue
        setup += r["tPCSetup"]
        asm += r["tAssemble"]
        conv += r["tConvert"]
        frz += r["tFreeze"]
        sN += sum(steps[i]["solves"])
        if steps[i]["reused"] == 0:
            nreb += 1
    return dict(setup=setup, asm=asm, conv=conv, frz=frz, nreb=nreb, sN=sN,
                total=setup + asm + conv + frz)


print("=" * 100)
print("★★★ CG 每迭代成本异常：精确核算")
print("=" * 100)

print(f"\n  {'K':>3} {'轮':>3} {'墙钟/s':>8} {'CG总/s':>8} {'apply累计/s':>11} "
      f"{'nApply':>7} {'每次apply/µs':>13}")
data = defaultdict(list)
for K in sorted(rows):
    for r in rows[K]:
        per = r["apply"] / r["napply"] * 1e6 if r["napply"] else 0
        print(f"  {K:>3} {r['rnd']:>3} {r['exe']:>8.2f} {r['solve']:>8.3f} "
              f"{r['apply']:>11.3f} {r['napply']:>7} {per:>13.2f}")
        data[K].append(r)

print(f"\n{'='*100}")
print("1. ★ 按 K 汇总（中位）")
print(f"{'='*100}")
print(f"  {'K':>3} {'墙钟/s':>9} {'CG总/s':>9} {'apply累计/s':>12} {'平均apply/µs':>14}")
agg = {}
for K in sorted(data):
    e = st.median([r["exe"] for r in data[K]])
    s = st.median([r["solve"] for r in data[K]])
    a = st.median([r["apply"] for r in data[K]])
    na = st.median([r["napply"] for r in data[K]])
    agg[K] = dict(e=e, s=s, a=a, na=na, per=a / na * 1e6 if na else 0)
    print(f"  {K:>3} {e:>9.2f} {s:>9.3f} {a:>12.3f} {agg[K]['per']:>14.2f}")

print(f"\n{'='*100}")
print("2. ★★ 关键：把 CG 总耗时拆开")
print(f"{'='*100}")
print(f"  {'K':>3} {'CG总/s':>9} {'预条件子(装配+分解+快照)/s':>26} {'apply累计/s':>12} "
      f"{'余项/s':>9} {'ΣN':>8} {'余项/迭代/µs':>13}")
for K in sorted(data):
    pb = precond(K, 1)
    a = agg[K]
    if not pb:
        continue
    # 预条件子非 apply 部分 = setup + asm + conv + frz
    other = pb["total"]
    # 余项 = CG总 − 预条件子非apply − apply累计
    resid = a["s"] - other - a["a"]
    sN = pb["sN"]
    per = resid / sN * 1e6 if sN else 0
    print(f"  {K:>3} {a['s']:>9.3f} {other:>26.3f} {a['a']:>12.3f} "
          f"{resid:>9.3f} {sN:>8} {per:>13.2f}")

print(f"""
  ★ 余项 = CG 总耗时 − 预条件子(装配+分解+快照) − apply累计
         = CG 的向量更新 + 内积(gSumProd) + 矩阵-向量乘(Amul) 等
""")

print(f"{'='*100}")
print("3. ★★★ 判定：每迭代的余项是否恒定？")
print(f"{'='*100}")
resids = {}
for K in sorted(data):
    pb = precond(K, 1)
    a = agg[K]
    if not pb:
        continue
    resid = a["s"] - pb["total"] - a["a"]
    resids[K] = resid / pb["sN"] * 1e6 if pb["sN"] else 0
    print(f"  K={K}: 余项/迭代 = {resids[K]:.2f} µs   (ΣN={pb['sN']})")

if len(resids) >= 2:
    vals = list(resids.values())
    print(f"\n  余项/迭代 的范围: [{min(vals):.2f}, {max(vals):.2f}] µs，"
          f"极差 {max(vals)-min(vals):.2f} µs")
    spread = (max(vals) - min(vals)) / st.mean(vals) * 100
    print(f"  相对极差 = {spread:.1f}%")
    if spread < 30:
        print(f"""
  ⇒ 余项/迭代【基本恒定】⇒ CG 自身的每迭代成本与 K 无关。
  ⇒ 因此"CG 每迭代成本随 K 下降"的表象【不成立】——
     它是我先前用"CG总耗时 − 预条件子总量"计算时的口径错误：
     预条件子总量里包含了 N·tIter（用孤立 tIter 估算），
     而孤立的 tIter（146 µs）比真实循环内的 apply（112-130 µs）偏高，
     且偏高幅度随 ΣN 放大 ⇒ 使 K=1 的余项被虚高。""")
    else:
        print(f"\n  ⇒ 余项/迭代不一致（相对极差 {spread:.1f}%）⇒ 存在与 K 相关的效应。")

print(f"\n{'='*100}")
print("4. ★ 修正后的收益口径")
print(f"{'='*100}")
print(f"  {'K':>3} {'墙钟/s':>9} {'相对K=1':>10} {'CG总/s':>9} {'相对K=1':>10} "
      f"{'apply累计/s':>12} {'相对K=1':>10}")
b = agg[1]
for K in sorted(agg):
    a = agg[K]
    print(f"  {K:>3} {a['e']:>9.2f} {(a['e']/b['e']-1)*100:>9.2f}% "
          f"{a['s']:>9.3f} {(a['s']/b['s']-1)*100:>9.2f}% "
          f"{a['a']:>12.3f} {(a['a']/b['a']-1)*100:>9.2f}%")

print(f"\n{'='*100}")
print("5. ★★ 每步重建次数与 apply 次数的关系")
print(f"{'='*100}")
print(f"  {'K':>3} {'重建数':>7} {'ΣN':>8} {'nApply':>8} {'nApply/ΣN':>10} "
      f"{'apply累计/s':>12}")
for K in sorted(data):
    pb = precond(K, 1)
    a = agg[K]
    if not pb:
        continue
    ratio = a["na"] / pb["sN"] if pb["sN"] else 0
    print(f"  {K:>3} {pb['nreb']:>7} {pb['sN']:>8} {a['na']:>8.0f} {ratio:>10.3f} "
          f"{a['a']:>12.3f}")
print("""
  ⚠️ nApply 应约等于 ΣN（CG 每次迭代调用一次 precondition）。
     若两者不等，说明有部分 apply 未被计入（如 pcorr 的求解）。
""")
