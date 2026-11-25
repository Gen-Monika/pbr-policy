#!/usr/bin/env python3
"""
★★★ 同源实验的完整核算：为什么墙钟最优是 K=3 而内部模型给 K=2？

═══════════════════════════════════════════════════════════════════════
数据（本次同源实验：墙钟与内部计时出自同一个进程）
═══════════════════════════════════════════════════════════════════════
  K=1: execTime 中位 15.24 s
  K=2:              13.70 s   (-10.1%)
  K=3:              12.33 s   (-19.1%)   ★ 墙钟最优
  K=5:              13.24 s   (-13.1%)
  K=8:              15.40 s   (+1.0%)

而内部成本模型（W = Σ tPCSetup + Σ N·tIter）给出 K*=2。

═══════════════════════════════════════════════════════════════════════
可能的分歧来源
═══════════════════════════════════════════════════════════════════════
(a) tIter 是【新分解】时的单次迭代代价（ma + mp）。
    但陈旧的预条件子会让 CG 的每步更贵 —— apply 的代价随年龄增长？
    ⇒ 若如此，则"陈旧"的代价被【低估】，最优 K 应更小，而非更大。
    ⇒ 与观测方向相反，故不是主因。
(b) 墙钟里还有一项随【重建次数】变化的开销（装配 + PETSc 对象管理）。
    本次已测得 t_assemble ≈ 0.77 ms/次。
(c) 测量噪声：每 K 只 3 轮，而机器状态有双峰。

⇒ 本脚本把同源 CSV 的四个分量全部核算，并做多元最小二乘拟合：
      T_wall ≈ O + α·ΣtPCSetup + β·n_rebuild + γ·ΣN·tIter
   以判定哪一项主导。
"""
import os
import re
import statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
# 21 列（新版，含 tAssemble）
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal").split(",")


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


def budget(K, rep):
    logp, csvp = f"samesrc/log.r{rep}k{K}", f"ss_k{K}_r{rep}.csv"
    if not (os.path.exists(logp) and os.path.exists(csvp)):
        return None
    steps, rows = parse_log(logp), load_csv(csvp)
    n = min(len(steps), len(rows))
    if n == 0:
        return None
    setup = asm = conv = frz = itr = 0.0
    nreb = 0
    sN = 0
    for i in range(n):
        r = rows[i]
        if r["tIter"] <= 0:
            continue
        setup += r["tPCSetup"]
        asm += r["tAssemble"]
        conv += r["tConvert"]
        frz += r["tFreeze"]
        ns = sum(steps[i]["solves"])
        sN += ns
        itr += ns * r["tIter"]
        if steps[i]["reused"] == 0:
            nreb += 1
    return dict(setup=setup, asm=asm, conv=conv, frz=frz, itr=itr, nreb=nreb,
                sN=sN, total=setup + asm + conv + frz + itr)


# 墙钟
wpat = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)")
wall = defaultdict(list)
for ln in open("ss.out"):
    m = wpat.search(ln)
    if m:
        wall[int(m.group(2))].append(float(m.group(4)))

print("=" * 100)
print("★★★ 同源实验核算（levels=10）")
print("=" * 100)

print(f"\n  {'K':>3} {'轮':>3} {'重建数':>7} {'ΣN':>8} {'Σsetup/s':>10} "
      f"{'Σasm/s':>9} {'Σconv/s':>9} {'ΣN·it/s':>9} {'内部合计/s':>11} "
      f"{'墙钟/s':>8}")
b = {}
for K in (1, 2, 3, 5, 8):
    for R in (1, 2, 3):
        x = budget(K, R)
        if x is None:
            continue
        b.setdefault(K, []).append(x)

# 墙钟按轮次对齐（wall 的字典顺序与脚本循环顺序一致）
order = {}
for ln in open("ss.out"):
    m = wpat.search(ln)
    if m:
        order.setdefault(int(m.group(2)), []).append(float(m.group(4)))

for K in sorted(b):
    for i, x in enumerate(b[K]):
        w = order[K][i] if i < len(order[K]) else float("nan")
        print(f"  {K:>3} {i+1:>3} {x['nreb']:>7} {x['sN']:>8} {x['setup']:>10.3f} "
              f"{x['asm']:>9.3f} {x['conv']:>9.3f} {x['itr']:>9.3f} "
              f"{x['total']:>11.3f} {w:>8.2f}")

print(f"\n{'='*100}")
print("1. 按 K 汇总（中位）")
print(f"{'='*100}")
print(f"  {'K':>3} {'重建数':>7} {'ΣN':>8} {'Σsetup/s':>10} {'Σasm/s':>9} "
      f"{'Σconv/s':>9} {'ΣN·it/s':>9} {'内部/s':>9} {'墙钟/s':>8} {'未解释/s':>10}")
rows = {}
for K in sorted(b):
    xs = b[K]
    agg = {k: st.median([x[k] for x in xs]) for k in xs[0]}
    w = st.median(order[K])
    unexp = w - agg["total"]
    rows[K] = dict(**agg, wall=w, unexp=unexp)
    print(f"  {K:>3} {agg['nreb']:>7.0f} {agg['sN']:>8.0f} {agg['setup']:>10.3f} "
          f"{agg['asm']:>9.3f} {agg['conv']:>9.3f} {agg['itr']:>9.3f} "
          f"{agg['total']:>9.3f} {w:>8.2f} {unexp:>10.3f}")

print(f"\n{'='*100}")
print("2. ★ 未解释部分与各候选量的相关性")
print(f"{'='*100}")
print("""  候选：(i) 重建次数 n_rebuild（每次重建的固定开销）
        (ii) ΣN（迭代总数）
        (iii) ΣtPCSetup（已计入，不计）""")
print(f"\n  {'K':>3} {'未解释/s':>10} {'重建数':>8} {'未解释/次重建/ms':>17} "
      f"{'ΣN':>8} {'未解释/ΣN/µs':>14}")
for K in sorted(rows):
    x = rows[K]
    per_reb = x["unexp"] / x["nreb"] * 1e3 if x["nreb"] else float("nan")
    per_N = x["unexp"] / x["sN"] * 1e6 if x["sN"] else float("nan")
    print(f"  {K:>3} {x['unexp']:>10.3f} {x['nreb']:>8.0f} "
          f"{per_reb:>17.2f} {x['sN']:>8.0f} {per_N:>14.2f}")

# 最小二乘：未解释 = α·n_rebuild + β·ΣN
ks = sorted(rows)
print(f"\n{'='*100}")
print("3. ★ 二元最小二乘：未解释 = α·n_rebuild + β·ΣN")
print(f"{'='*100}")
try:
    import numpy as np
    A_ = np.array([[rows[K]["nreb"], rows[K]["sN"]] for K in ks], dtype=float)
    y = np.array([rows[K]["unexp"] for K in ks], dtype=float)
    coef, res, rank, sv = np.linalg.lstsq(A_, y, rcond=None)
    a_, b_ = coef
    print(f"  α (每次重建) = {a_*1e3:+.3f} ms")
    print(f"  β (每次迭代) = {b_*1e6:+.3f} µs")
    print(f"\n  {'K':>3} {'实测未解释/s':>13} {'拟合值/s':>10} {'残差/s':>9}")
    for K in ks:
        fit = a_ * rows[K]["nreb"] + b_ * rows[K]["sN"]
        print(f"  {K:>3} {rows[K]['unexp']:>13.3f} {fit:>10.3f} "
              f"{rows[K]['unexp']-fit:>9.3f}")
    print("\n  ⚠️ 但 n_rebuild 与 ΣN 高度负相关（重建越少 ⇒ 迭代越多），")
    print("     故两个系数难以独立辨识。需更多 K 值或更强的设计。")
except ImportError:
    print("  （无 numpy，跳过）")

print(f"\n{'='*100}")
print("4. ★★ 墙钟排序 vs 内部模型排序")
print(f"{'='*100}")
print(f"  {'K':>3} {'墙钟实测':>10} {'内部模型':>10} {'墙钟相对K=1':>12} "
      f"{'内部相对K=1':>12} {'分歧/pp':>9}")
w1 = rows[1]["wall"]
i1 = rows[1]["total"]
for K in ks:
    wrel = (rows[K]["wall"] / w1 - 1) * 100
    irel = (rows[K]["total"] / i1 - 1) * 100
    print(f"  {K:>3} {rows[K]['wall']:>10.2f} {rows[K]['total']:>10.3f} "
          f"{wrel:>11.2f}% {irel:>11.2f}% {wrel-irel:>+9.2f}")

bw = min(ks, key=lambda K: rows[K]["wall"])
bi = min(ks, key=lambda K: rows[K]["total"])
print(f"\n  ⇒ 墙钟最优 K = {bw}")
print(f"  ⇒ 内部模型最优 K = {bi}")
print(f"  ⇒ {'两者一致 ✓' if bw == bi else '两者不一致 ✗'}")

print(f"\n{'='*100}")
print("5. ★★ 全因子核算：是否还有剩余未解释？")
print(f"{'='*100}")
print("""  若把 t_assemble 也计入（本次已测），则内部合计为：
      Σsetup + Σasm + Σconv + Σfreeze + ΣN·tIter
  再看剩余未解释量是否仍随 K 系统性变化。""")
print(f"\n  {'K':>3} {'含asm的内部合计/s':>18} {'墙钟/s':>8} {'未解释/s':>10} "
      f"{'未解释为墙钟的':>15}")
for K in ks:
    x = rows[K]
    tot = x["setup"] + x["asm"] + x["conv"] + x["frz"] + x["itr"]
    un = x["wall"] - tot
    print(f"  {K:>3} {tot:>18.3f} {x['wall']:>8.2f} {un:>10.3f} "
          f"{un/x['wall']*100:>14.1f}%")

print(f"\n{'='*100}")
print("6. 结论")
print(f"{'='*100}")
K1 = rows[1]
tot1 = K1["setup"] + K1["asm"] + K1["conv"] + K1["frz"] + K1["itr"]
print(f"""
  预条件子相关开销（含装配）占墙钟比例：
      K=1: {tot1:.3f}/{K1['wall']:.2f} = {tot1/K1['wall']*100:.1f}%
""")
for K in ks:
    x = rows[K]
    tot = x["setup"] + x["asm"] + x["conv"] + x["frz"] + x["itr"]
    print(f"      K={K}: {tot:.3f}/{x['wall']:.2f} = {tot/x['wall']*100:.1f}%")
print("""
  ⇒ 若占比仅 ~30%，则墙钟收益的【上限】是 30% 量级，
     实测最优 -19.1% 是这一上限的 64%，属合理范围。
""")
