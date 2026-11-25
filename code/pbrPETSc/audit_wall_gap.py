#!/usr/bin/env python3
"""
★ 追查：为什么墙钟节省（3.78 s）是内部计时预测（1.64 s）的 2.3 倍？

═══════════════════════════════════════════════════════════════════════
已知数据（levels=10, K=1 vs K=2）
═══════════════════════════════════════════════════════════════════════
  内部计时合计： 4.500 s  →  2.860 s   节省 1.640 s
  墙钟实测中位：15.10 s  →  11.32 s   节省 3.780 s
  ⇒ 差 2.140 s 未被内部计时解释

内部计时的分量：
  tPCSetup   2.896 → 1.455 s  （节省 1.441，已被计入）
  tConvert   0.356 → 0.246 s  （节省 0.110）
  tFreeze    0.078 → 0.026 s
  N·tIter    1.171 → 1.133 s

可能被漏掉的来源：
  (a) PETSc 的 Mat 对象创建/销毁（每次重建都建一个新 Mat）
  (b) 快照文件的写入（tFreeze 只计了写盘函数本身，可能不含 flush）
  (c) 内存分配/释放（ILU(10) 的填充很大）
  (d) 迭代数变化引起的其他求解器联动
  (e) 测量本身：`tPCSetup` 的计时区间是否覆盖了完整的分解过程？

本脚本检验 (e)：把日志中 PETSc 行给出的 t_pcsetup 与
CSV 中的 tPCSetup 逐行对照，并检查 t_freeze/t_convert 的量级。
"""
import os
import re
import statistics as st
from collections import defaultdict

LOGPAT = re.compile(
    r"PETSc ilu lvl=\d+\"?\s*(rebuild|REUSE@\d+)\"?\s*:"
    r"\s*t_freeze=([0-9.]+)us\s+t_convert=([0-9.]+)us"
    r"\s+t_pcsetup=([0-9.]+)us\s+r=([0-9.eE+-]+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")


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


def load_log(path):
    out = []
    for ln in open(path, errors="ignore"):
        m = LOGPAT.search(ln)
        if m:
            out.append(dict(reused=0 if m.group(1) == "rebuild" else 1,
                            tfreeze=float(m.group(2)) * 1e-6,
                            tconvert=float(m.group(3)) * 1e-6,
                            tsetup=float(m.group(4)) * 1e-6))
    return out


print("=" * 96)
print("★ 追查未解释的 2.14 s")
print("=" * 96)

for K in (1, 2):
    csvp, logp = f"l10_k{K}_r1.csv", f"l10/log.k{K}r1"
    rows, lg = load_csv(csvp), load_log(logp)
    n = min(len(rows), len(lg))
    print(f"\n  ── K={K} ──")
    print(f"    CSV 行 {len(rows)}，日志行 {len(lg)}，比对 {n}")

    ds, dc, df = [], [], []
    for i in range(n):
        ds.append(lg[i]["tsetup"] - rows[i]["tPCSetup"])
        dc.append(lg[i]["tconvert"] - rows[i]["tConvert"])
        df.append(lg[i]["tfreeze"] - rows[i]["tFreeze"])
    print(f"    t_pcsetup(日志) − tPCSetup(CSV)：中位 {st.median(ds)*1e6:+.3f} µs，"
          f"最大 {max(ds)*1e6:+.3f}")
    print(f"    t_convert(日志) − tConvert(CSV)：中位 {st.median(dc)*1e6:+.3f} µs")
    print(f"    t_freeze(日志)  − tFreeze(CSV) ：中位 {st.median(df)*1e6:+.3f} µs")

    nreb = sum(1 for x in lg if x["reused"] == 0)
    print(f"    重建步数 {nreb}")
    print(f"    ΣtPCSetup  = {sum(r['tPCSetup'] for r in rows):.4f} s")
    print(f"    ΣtConvert  = {sum(r['tConvert'] for r in rows):.4f} s")
    print(f"    ΣtFreeze   = {sum(r['tFreeze'] for r in rows):.4f} s")

print(f"\n{'='*96}")
print("★ 结论性核算：内部计时覆盖了什么、没覆盖什么")
print(f"{'='*96}")
print("""
  tPCSetup 的计时区间（源码）：
      c0 = wallSeconds();
      PCSetOperators + PCSetUp ...
      tPCSetup_ = wallSeconds() - c0;
  ⇒ 覆盖 PETSc 的分解本身。

  ⚠️ 但【不覆盖】：
      - buildPETScMatrix()：把 OpenFOAM 的 ldu 矩阵装配成 PETSc 的 CSR
        （含 malloc、MPI 无关的本地拷贝）
      - Mat 的创建：每次重建都 MatCreate + MatSetValues + MatAssembly
      - 旧 Mat/PC 的销毁
      - 快照文件的 fwrite + flush

  其中 buildPETScMatrix 是最可疑的一项：ILU(10) 的填充使
  nnz 大幅增加，而装配 CSR 的成本随 nnz 增长。
""")

# 估算 buildPETScMatrix 的开销：从 nCells/nFaces 与 levels 推断 nnz
print("  装配成本的可疑性检验：")
print(f"    levels=10 的 tPCSetup（含分解）= {st.median([r['tPCSetup'] for r in load_csv('l10_k1_r1.csv') if r['tPCSetup']>1e-4])*1e6:.0f} µs")
print(f"    levels=5  的 tPCSetup           = 2920 µs")
print(f"    levels=2  的 tPCSetup           = 1259 µs")
print("""    ⇒ 分解成本随 levels 陡增（9.84→58.06 的 r 即反映此），
       而装配成本对 levels 不敏感（矩阵本身不变）。
    ⇒ 若墙钟节省远超内部预测，最可能是【PETSc 对象管理】
       （Mat/PC 创建销毁、内存分配）未被计入。""")
