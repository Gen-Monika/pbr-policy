#!/usr/bin/env python3
"""
★ 定量拆解墙钟节省与内部计时预测之间的 2.14 s 差额。

═══════════════════════════════════════════════════════════════════════
已知
═══════════════════════════════════════════════════════════════════════
  K=1: 内部合计 4.500 s   墙钟中位 15.10 s
  K=2: 内部合计 2.860 s   墙钟中位 11.32 s
  内部节省 1.640 s  vs  墙钟节省 3.780 s   ⇒ 差 2.140 s

若"未计时的每步开销"与重建次数成正比：
      未计时开销 = n_rebuild × c
  K=1: 344c
  K=2: 222c
  ⇒ 差额 = (344 − 222)·c = 122c = 2.140 s  ⇒ c ≈ 17.5 ms/次

检验这个假设：用 K=3 的数据。
  K=3: 重建 181 次，内部合计 3.537 s
  ⇒ 预测墙钟 = 3.537 + 181×0.0175 + O
  而由 K=1 可定出 O：15.10 − 4.500 − 344×0.0175 = 15.10 − 4.500 − 6.02 = 4.58 s
  ⇒ K=3 预测墙钟 = 3.537 + 3.17 + 4.58 = 11.29 s
  实测 K=3 = 11.59 s   ⇒ 吻合（差 0.3 s，2.6%）

⇒ 若假设成立，则"每次重建的未计时开销"约 17.5 ms，
  远大于被计时的 tPCSetup（K=1 时 2.896s/344 = 8.4 ms）。
  ⇒ 说明真正的大头在【未被计时的部分】。
"""
import os
import re
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")


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


def count_solves(path):
    steps, cur = [], 0
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            steps.append(cur)
            cur = 0
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur += int(ms.group(1))
    steps.append(cur)
    return steps[1:] if steps else []


def internal(K, rep=1):
    logp, csvp = f"l10/log.k{K}r{rep}", f"l10_k{K}_r{rep}.csv"
    if not (os.path.exists(logp) and os.path.exists(csvp)):
        return None
    rows, Ns = load_csv(csvp), count_solves(logp)
    n = min(len(rows), len(Ns))
    setup = sum(rows[i]["tPCSetup"] for i in range(n))
    conv = sum(rows[i]["tConvert"] for i in range(n))
    frz = sum(rows[i]["tFreeze"] for i in range(n))
    it = sum(Ns[i] * rows[i]["tIter"] for i in range(n) if rows[i]["tIter"] > 0)
    nreb = sum(1 for i in range(n) if rows[i]["reused"] == 0)
    return dict(nreb=nreb, setup=setup, conv=conv, frz=frz, it=it,
                total=setup + conv + frz + it)


# 墙钟
wpat = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)")
wall = defaultdict(list)
for ln in open("l10wt.out"):
    m = wpat.search(ln)
    if m:
        wall[int(m.group(2))].append(float(m.group(4)))

print("=" * 96)
print("★ 差额拆解：每次重建的未计时开销")
print("=" * 96)

comp = {}
print(f"\n  {'K':>3} {'重建数':>7} {'内部合计/s':>12} {'墙钟中位/s':>11} "
      f"{'未解释/s':>10} {'每次重建/s':>11}")
for K in (1, 2, 3):
    c = internal(K)
    if not c or K not in wall:
        continue
    comp[K] = c
    w = st.median(wall[K])
    comp[K]["wall"] = w

# 用 K=1, K=2 联立解出 c（每次重建的未计时开销）与 O（与重建无关的部分）
c1, c2 = comp[1], comp[2]
dn = c1["nreb"] - c2["nreb"]
dw = c1["wall"] - c2["wall"]
dcost = c1["total"] - c2["total"]
if dn > 0:
    c_extra = (dw - dcost) / dn
    O = c1["wall"] - c1["total"] - c1["nreb"] * c_extra
    print(f"\n  由 K=1 与 K=2 联立：")
    print(f"    重建次数差 Δn = {dn}")
    print(f"    墙钟差 ΔT     = {dw:.3f} s")
    print(f"    内部计时差    = {dcost:.3f} s")
    print(f"    ⇒ 每次重建的【未计时】开销 c = (ΔT − Δcost)/Δn = {c_extra*1e3:.2f} ms")
    print(f"    ⇒ 与重建无关的固定部分 O = {O:.3f} s")
    print(f"\n  对照：被计时的每次重建开销 = tPCSetup 中位 = "
          f"{st.median([r['tPCSetup'] for r in load_csv('l10_k1_r1.csv') if r['tPCSetup']>1e-4])*1e3:.2f} ms")
    print(f"  ⇒ 未计时部分是被计时部分的 "
          f"{c_extra/st.median([r['tPCSetup'] for r in load_csv('l10_k1_r1.csv') if r['tPCSetup']>1e-4]):.1f} 倍")

    # 用 K=3 检验
    if 3 in comp:
        c3 = comp[3]
        pred = c3["total"] + c3["nreb"] * c_extra + O
        print(f"\n  ★ 检验（用 K=3 外推，未参与拟合）：")
        print(f"    预测墙钟 = {pred:.3f} s")
        print(f"    实测墙钟 = {c3['wall']:.3f} s")
        print(f"    偏差     = {(pred/c3['wall']-1)*100:+.2f}%")
        print(f"    ⇒ {'假设成立 ✓' if abs(pred/c3['wall']-1) < 0.05 else '假设不成立 ✗'}")

    print(f"\n{'='*96}")
    print("★ 结论")
    print(f"{'='*96}")
    print(f"""
  存在一项随每次重建发生、约 {c_extra*1e3:.0f} ms 的开销【未被内部计时捕获】。
  它的量级是被计时的 tPCSetup 的 {c_extra/st.median([r['tPCSetup'] for r in load_csv('l10_k1_r1.csv') if r['tPCSetup']>1e-4]):.1f} 倍。

  最可能的来源（按可疑度排序）：
    1. buildPETScMatrix()：ldu → CSR 装配（MatCreate/MatSetValues/MatAssembly）
       源码中此调用在 tPCSetup 计时区间【之外】
    2. PETSc Mat/PC 的创建与销毁，以及 ILU(10) 大填充的内存分配/释放
    3. 快照文件写入的 flush 部分（tFreeze 只计了 fwrite 调用本身）

  ★ 对论文的含意：
    这【加强了】结论 —— 重建的实际代价比 r 所反映的更高，
    因此"复用"的真实收益比成本模型预测的更大。
    ⇒ 用 r 作为决策指标是【保守】的。
""")

with open("audit_conclusion.txt", "w") as f:
    f.write(f"c_extra_ms = {c_extra*1e3:.2f}\n")
    f.write(f"O_s = {O:.3f}\n")
