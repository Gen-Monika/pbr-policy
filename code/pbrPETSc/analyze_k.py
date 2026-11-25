#!/usr/bin/env python3
"""
K 扫描的最终分析：用【迭代数当量】消除机器状态的双峰噪声。

★ 诊断结论（见 diag_scan.py）：
  - 同一 K 的各重复：N 序列【逐位相同】⇒ 冻结决策完全决定迭代数，确定性极强。
  - 但 tIter 与 tPCSetup 出现双峰（56.2µs vs 46.3-47.6µs；1255µs vs 875-955µs），
    这是机器状态差异，与 K 无关。
  ⇒ 因此 ΣN·tIter 不是跨 K 可比的量，必须换成无量纲的"迭代数当量"。

★ 口径：
     cost(K) = ΣN(step) + N_rebuild × r        [单位：一次迭代]

     与之前 W = ΣtPCSetup + ΣN·tIter 的关系：
       两者只差一个全局因子 tIter，故【比较 K 的相对优劣时完全等价】，
       但本口径把 tIter 的机器漂移从比较中彻底剔除。

     r = tPCSetup / tIter，用【同一次运行内】的中位数（消除跨运行机器状态差异）

★ 判据（一阶最优条件）：
     cost(K+1) ≤ cost(K)  ⟺  续用一步的收益 ≥ 它的成本
"""
import os
import re
import statistics as st

HDR20 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
         "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")


def load_csv(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        if len(p) != 20:
            continue
        d = {}
        try:
            for k, v in zip(HDR20, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


def load_N(logpath):
    pat = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
    N = []
    for ln in open(logpath, errors="ignore"):
        if "p_rgh" not in ln:
            continue
        m = pat.search(ln)
        if m:
            N.append(int(m.group(1)))
    return N


def run_metrics(K, rep):
    """返回单次运行的 (ΣN, 重建次数, 同运行内 r, cost当量)。"""
    csvp, logp = f"s_k{K}_r{rep}.csv", f"s{K}/log.s{rep}"
    if not (os.path.exists(csvp) and os.path.exists(logp)):
        return None
    rows, N = load_csv(csvp), load_N(logp)
    n = min(len(rows), len(N))
    rows, N = rows[:n], N[:n]
    if n == 0:
        return None
    # 同一次运行内的 r：只用真正分解的步（排除复用时的 ~1µs 残留）
    reb = [d for d in rows if d["reused"] == 0]
    ts = st.median([d["tPCSetup"] for d in reb]) if reb else float("nan")
    ti = st.median([d["tIter"] for d in rows])
    r_local = ts / ti if (ti and ti > 0) else float("nan")
    sN = sum(N)
    nreb = len(reb)
    cost = sN + nreb * r_local
    return dict(K=K, rep=rep, n=n, sN=sN, nreb=nreb, r=r_local,
                ts=ts, ti=ti, cost=cost, N=N, rows=rows)


def main():
    print("=" * 90)
    print("K 扫描最终分析（迭代数当量口径，消除机器状态双峰）")
    print("=" * 90)

    runs = {}
    print(f"\n{'K':>2} {'rep':>3} {'ΣN':>7} {'重建':>5} {'r(同运行内)':>12} "
          f"{'cost=ΣN+nreb·r':>15} {'相对K=1':>10}")
    for K in (1, 2, 3, 4, 5, 6, 8):
        for rep in (1, 2, 3):
            m = run_metrics(K, rep)
            if m is None:
                continue
            runs.setdefault(K, []).append(m)
    # K=1 基线（三次平均）
    base = st.mean([m["cost"] for m in runs[1]]) if 1 in runs else None
    for K in sorted(runs):
        for m in runs[K]:
            rel = f"{(m['cost']/base-1)*100:+9.2f}%" if base else ""
            print(f"{m['K']:>2} {m['rep']:>3} {m['sN']:>7} {m['nreb']:>5} "
                  f"{m['r']:>12.2f} {m['cost']:>15.1f} {rel:>10}")

    print(f"\n{'='*90}")
    print("按 K 汇总（三次重复的中位数）")
    print(f"{'='*90}")
    print(f"{'K':>2} {'cost中位':>11} {'相对K=1':>10} {'ΣN中位':>9} {'重建中位':>9} "
          f"{'r中位':>8} {'每步迭代中位':>13}")
    med = {}
    for K in sorted(runs):
        c = st.median([m["cost"] for m in runs[K]])
        sN = st.median([m["sN"] for m in runs[K]])
        nr = st.median([m["nreb"] for m in runs[K]])
        rr = st.median([m["r"] for m in runs[K]])
        med[K] = c
        rel = f"{(c/base-1)*100:+9.2f}%" if base else ""
        print(f"{K:>2} {c:>11.1f} {rel:>10} {sN:>9.0f} {nr:>9.0f} {rr:>8.2f} "
              f"{sN/344:>13.2f}")

    if med:
        best = min(med, key=med.get)
        print(f"\n⇒ 最优 K = {best}   cost = {med[best]:.1f}  "
              f"（K=1 为 {med[1]:.1f}，收益 {(med[best]/med[1]-1)*100:+.2f}%）")

    # ---- 年龄曲线 ----
    print(f"\n{'='*90}")
    print("年龄曲线 N(age)（用 K=1 的确定性 N 序列作基线，全部重复逐位相同，取一次即可）")
    print(f"{'='*90}")
    m1 = runs[1][0]
    N1 = m1["N"]
    print(f"  K=1 基线（每步重建，age 恒为 0）: ΣN={m1['sN']}, 均值={m1['sN']/len(N1):.2f}")

    print(f"\n  {'step':>5} " + "".join(f"{'K='+str(K):>9}" for K in (1, 2, 3, 5, 8)))
    for i in (100, 101, 102, 103, 104, 105, 110, 120, 150, 200, 250, 300, 340):
        if i >= len(N1):
            continue
        line = f"  {i:>5} "
        for K in (1, 2, 3, 5, 8):
            if K in runs and i < len(runs[K][0]["N"]):
                line += f"{runs[K][0]['N'][i]:>9}"
        print(line)

    # 累计劣化
    print(f"\n  {'步段':>12} " + "".join(f"{'K='+str(K):>10}" for K in (1, 2, 3, 5, 8)))
    for a, b in ((0, 99), (100, 149), (150, 199), (200, 249), (250, 343)):
        line = f"  {f'{a}-{b}':>12} "
        for K in (1, 2, 3, 5, 8):
            if K in runs:
                seg = runs[K][0]["N"][a:b+1]
                line += f"{sum(seg)/len(seg):>10.2f}"
        print(line)
    print("  （表中为各步段的平均迭代数）")

    # ---- 判据 ----
    print(f"\n{'='*90}")
    print("判据：cost(K+1) 是否优于 cost(K)")
    print(f"{'='*90}")
    for K in sorted(med):
        nxt = K + 1
        if nxt in med:
            print(f"  K={K} → {nxt}: cost {med[K]:.1f} → {med[nxt]:.1f}  "
                  f"{'改善 ✓' if med[nxt] < med[K] else '变差 ✗'}")


if __name__ == "__main__":
    main()
