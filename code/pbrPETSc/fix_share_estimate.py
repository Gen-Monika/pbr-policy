#!/usr/bin/env python3
"""
修正 §4 的占比推算。

═══════════════════════════════════════════════════════════════════════
上一版的错误
═══════════════════════════════════════════════════════════════════════
用了 r（只含 tPCSetup）当内部收益，得出占比 136%（>100%，不可能）。

原因：
  1. 内部"收益" = (W_K − W_1)/W_1，其中 W 是预条件子相关总开销。
     把 W_1 当作分母，得到的其实是"预条件子部分的相对变化"，
     而想求的占比应以【整个求解的墙钟】为分母。
  2. 更重要的是：重建带来的开销不止 tPCSetup，还有
     tConvert（矩阵装配/转换，约 1019 µs）与 tFreeze（快照写入）。
     冻结策略一次性省掉的正是这些。

正确的推算式：
    设 S = 预条件子相关开销（含 setup/convert/freeze/apply 全部）
       T = 整个求解墙钟（除预条件子外的部分记为 O）
       S + O = T
    K=1 时（每步重建）S_1 最大；K=2 时 S_2 较小。
    墙钟收益 g_wall = (S_2 + O)/(S_1 + O) − 1
    ⇒ 由实测 g_wall 与计算出的 S_1、S_2 可反解 O，进而得占比。
"""
import os
import re
import statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")


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
        if len(p) != 20:
            continue
        d = {}
        try:
            for k, v in zip(CSV_HDR, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


def component_costs(K, rep=1):
    """把一个 K 运行的预条件子相关开销拆成各分量。"""
    logp, csvp = f"l10/log.k{K}r{rep}", f"l10_k{K}_r{rep}.csv"
    if not (os.path.exists(logp) and os.path.exists(csvp)):
        return None
    steps, rows = parse_log(logp), load_csv(csvp)
    n = min(len(steps), len(rows))
    setup = conv = frz = iters = 0.0
    nreb = 0
    for i in range(n):
        r = rows[i]
        if r["tIter"] <= 0:
            continue
        setup += r["tPCSetup"]
        conv += r["tConvert"]
        frz += r["tFreeze"]
        iters += sum(steps[i]["solves"]) * r["tIter"]
        if steps[i]["reused"] == 0:
            nreb += 1
    return dict(setup=setup, conv=conv, frz=frz, iters=iters, nreb=nreb,
                total=setup + conv + frz + iters)


print("=" * 96)
print("★ levels=10 预条件子开销的分量拆分")
print("=" * 96)
print(f"  {'K':>3} {'重建数':>7} {'tPCSetup/s':>11} {'tConvert/s':>11} "
      f"{'tFreeze/s':>10} {'N·tIter/s':>11} {'合计/s':>9}")
comp = {}
for K in (1, 2, 3):
    c = component_costs(K)
    if c:
        comp[K] = c
        print(f"  {K:>3} {c['nreb']:>7} {c['setup']:>11.3f} {c['conv']:>11.3f} "
              f"{c['frz']:>10.3f} {c['iters']:>11.3f} {c['total']:>9.3f}")

if len(comp) >= 2:
    print(f"\n  相对 K=1 的变化：")
    print(f"  {'K':>3} {'tPCSetup':>10} {'tConvert':>10} {'tFreeze':>10} "
          f"{'N·tIter':>10} {'合计':>10}")
    for K in sorted(comp):
        c1 = comp[1]
        print(f"  {K:>3} "
              f"{(comp[K]['setup']/c1['setup']-1)*100:>9.2f}% "
              f"{(comp[K]['conv']/c1['conv']-1)*100:>9.2f}% "
              f"{(comp[K]['frz']/c1['frz']-1)*100:>9.2f}% "
              f"{(comp[K]['iters']/c1['iters']-1)*100:>9.2f}% "
              f"{(comp[K]['total']/c1['total']-1)*100:>9.2f}%")

    # 实测墙钟
    wpat = re.compile(r"K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)")
    ext = defaultdict(list)
    for ln in open("l10wt.out"):
        m = wpat.search(ln)
        if m:
            ext[int(m.group(1))].append(float(m.group(3)))
    base = st.median(ext[1])

    print(f"\n{'='*96}")
    print("★ 占比反解（修正版）")
    print(f"{'='*96}")
    print("""
  设预条件子相关开销 S（= setup + convert + freeze + 迭代），
  其余部分为 O（动量预测、湍流、界面输运、I/O 等）。
      T_K = S_K + O
      墙钟收益 g_wall = T_K/T_1 − 1

  ⇒ O = (S_K − S_1·(1+g_wall)) / g_wall
""")
    for K in (2, 3):
        if K not in comp:
            continue
        g = st.median(ext[K]) / base - 1
        S1, SK = comp[1]["total"], comp[K]["total"]
        if abs(g) < 1e-9:
            continue
        O = (SK - S1 * (1 + g)) / g
        T1 = S1 + O
        print(f"  K={K}: 墙钟收益 g = {g*100:+.2f}%")
        print(f"       S_1 = {S1:.3f}s, S_K = {SK:.3f}s")
        print(f"       ⇒ O = {O:.3f}s,  T_1 = {T1:.3f}s")
        print(f"       ⇒ 预条件子占比 = S_1/T_1 = {S1/T1*100:.1f}%")
        print(f"       ⇒ 与墙钟实测中位 {st.median(ext[1]):.2f}s 对照 "
              f"(模型 T_1 = {T1:.2f}s)")
        print()

    print("""  ⚠️ 注意：S 的单位是"solver 内部计时之和"，而 T 是求解器自报的
     ExecutionTime。两者口径接近但不是同一测法，故占比只是数量级估计。""")
