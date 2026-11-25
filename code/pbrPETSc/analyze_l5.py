#!/usr/bin/env python3
"""
ILU(5) 扫描的完整分析（与 analyze_final2.py / analyze_phase.py 同口径）。

检验目标：levels=5 的 r = 36.56 是否越过了"每步 3 次求解"的门限
          （ΔN_step(1) ≈ 33–38 ⇒ 需要 r > 33）。
若越过，则固定周期最优 K* 应显著大于 1，且在线策略的空间更大。
"""
import os
import re
import json
import statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
REUSE_RE = re.compile(r"REUSE@(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
T_MAX = 344


def parse_log(path):
    steps, cur = [], None
    for ln in open(path, errors="ignore"):
        m = TIME_RE.match(ln)
        if m:
            if cur is not None:
                steps.append(cur)
            cur = dict(t=float(m.group(1)), reused=None, b=None, solves=[])
            continue
        if cur is None:
            continue
        if "PETSc ilu lvl" in ln:
            if "REUSE@" in ln:
                cur["reused"] = 1
                mm = REUSE_RE.search(ln)
                cur["b"] = int(mm.group(1)) if mm else None
            else:
                cur["reused"] = 0
            continue
        ms = SOLVE_RE.search(ln)
        if ms:
            cur["solves"].append(int(ms.group(1)))
    if cur is not None:
        steps.append(cur)
    for i, s in enumerate(steps, start=1):
        if s["reused"] == 0:
            s["b"] = i
    return steps


def load_csv(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        cols = (CSV_HDR if len(p) == 20
                else CSV_HDR[:11] + CSV_HDR[12:] if len(p) == 19 else None)
        if cols is None:
            continue
        d = {}
        try:
            for k, v in zip(cols, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


def load_run(logp, csvp):
    if not (os.path.exists(logp) and os.path.exists(csvp)):
        return []
    steps, rows = parse_log(logp), load_csv(csvp)
    n = min(len(steps), len(rows))
    out = []
    for i in range(n):
        s, r = steps[i], rows[i]
        if r["tIter"] <= 0:
            continue
        out.append(dict(t=i + 1, b=s["b"] or (i + 1), reused=s["reused"],
                        solves=s["solves"], Nsum=sum(s["solves"]),
                        tsetup=r["tPCSetup"], titer=r["tIter"],
                        r=r["tPCSetup"] / r["tIter"]))
    return out


def main():
    print("=" * 100)
    print("ILU(5) 扫描分析")
    print("=" * 100)

    # L5 数据
    l5 = {}
    for K in (1, 2, 3, 4, 5, 6, 8):
        runs = [load_run(f"l5/log.k{K}r{R}", f"l5_k{K}_r{R}.csv") for R in (1, 2, 3)]
        runs = [r for r in runs if r]
        if runs:
            l5[K] = runs
    bigs = [load_run(f"l5/log.big{R}", f"l5_big_r{R}.csv") for R in (1, 2)]
    bigs = [b for b in bigs if b]

    if not l5:
        print("  L5 数据尚未就绪")
        return

    print(f"\n  L5 载入：K ∈ {sorted(l5)}，大年龄 {len(bigs)} 份")

    # ── 1. r ──
    rs = []
    for K, runs in l5.items():
        for run in runs:
            for d in run:
                if d["reused"] == 0 and d["tsetup"] > 1e-4:
                    rs.append(d["r"])
    r0 = st.median(rs)
    print(f"\n  ★ L5 的 r = {r0:.2f}（n={len(rs)}）")

    # ── 2. 实测代价 ──
    print(f"\n{'='*100}")
    print("1. 实测代价（无相位歧义口径）")
    print(f"{'='*100}")
    print(f"  {'K':>3} {'重建数(中位)':>11} {'Σr(中位)':>10} {'ΣN(中位)':>10} "
          f"{'cost(中位)':>11} {'相对K=1':>10} {'ΣN 极差(3次)':>13}")
    real = {}
    for K in sorted(l5):
        cs, srs, sns, nrs = [], [], [], []
        for run in l5[K]:
            sr = sum(d["r"] for d in run if d["r"])
            sn = sum(d["Nsum"] for d in run)
            srs.append(sr)
            sns.append(sn)
            cs.append(sr + sn)
            nrs.append(sum(1 for d in run if d["reused"] == 0))
        real[K] = st.median(cs)
        print(f"  {K:>3} {st.median(nrs):>11.0f} {st.median(srs):>10.1f} "
              f"{st.median(sns):>10.0f} {st.median(cs):>11.1f} "
              f"{'':>10}{max(sns)-min(sns):>13}")
    for K in sorted(real):
        if 1 in real:
            print(f"    K={K}: {(real[K]/real[1]-1)*100:+7.2f}%")
    print(f"\n  ⇒ 实测最优 K = {min(real, key=real.get)}")

    # ── 3. 建表（L5） ──
    cells = defaultdict(list)
    for K, runs in l5.items():
        for run in runs:
            for d in run:
                cells[(d["t"], d["t"] - d["b"])].append(d["Nsum"])
    for run in bigs:
        for d in run:
            cells[(d["t"], d["t"] - d["b"])].append(d["Nsum"])
    tab = {k: st.median(v) for k, v in cells.items()}
    amax = max(a for (_, a) in tab)
    print(f"\n  表：{len(tab)} 格，a ∈ [0, {amax}]")

    def Nfn(t, a):
        if (t, a) in tab:
            return tab[(t, a)]
        st_ = [(abs(aa - a), v) for (tt, aa), v in tab.items() if tt == t]
        if st_:
            return min(st_)[1]
        bya = [v for (tt, aa), v in tab.items() if aa == a]
        if bya:
            return st.median(bya)
        return st.median(list(tab.values()))

    # ── 4. 年龄曲线与判据 ──
    print(f"\n{'='*100}")
    print("2. ★ 年龄曲线与时间分辨判据")
    print(f"{'='*100}")
    bya = defaultdict(list)
    for (t, a), v in tab.items():
        bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    print(f"  {'a':>3} {'N_step':>9} {'ΔN':>8} {'vs r':>9} {'判定':>6}")
    for a in sorted(curve)[:12]:
        dn = curve[a] - curve[0]
        f = "—" if a == 0 else ("复用" if dn < r0 else "重建")
        print(f"  {a:>3} {curve[a]:>9.1f} {dn:>8.1f} {dn-r0:>+9.1f} {f:>6}")

    a0 = {t: tab[(t, 0)] for (t, a) in tab if a == 0}
    a1 = defaultdict(list)
    for (t, a), v in tab.items():
        if a == 1:
            a1[t].append(v)
    common = sorted(set(a0) & set(a1))
    print(f"\n  ΔN_step(0→1) 的时间分辨（r = {r0:.1f}）：")
    print(f"  {'步段':>12} {'ΔN 中位':>10} {'样本':>6} {'判定':>6}")
    for lo, hi in ((101, 150), (151, 200), (201, 250), (251, 300), (301, 344)):
        ds = [st.median(a1[t]) - a0[t] for t in common if lo <= t <= hi]
        if ds:
            m = st.median(ds)
            print(f"  {f'{lo}-{hi}':>12} {m:>10.1f} {len(ds):>6} "
                  f"{'复用' if m < r0 else '重建':>6}")

    # ── 5. 策略对比 ──
    print(f"\n{'='*100}")
    print("3. ★ 策略对比")
    print(f"{'='*100}")

    def sim_always():
        return sum(r0 + Nfn(t, 0) for t in range(1, T_MAX + 1))
    base = sim_always()

    def sim_phase(K, b0):
        tot, a = 0.0, 0
        for t in range(1, T_MAX + 1):
            if (t < b0) or ((t - b0) % K == 0):
                tot += r0 + Nfn(t, 0)
                a = 1
            else:
                tot += Nfn(t, a)
                a += 1
        return tot

    print(f"  P1 每步重建：{base:.1f}")
    print(f"\n  {'K':>3} {'相位A(b0=100)':>14} {'相对P1':>10}   {'相位B(b0=1)':>13} {'相对P1':>10}")
    A, B = {}, {}
    for K in range(1, 13):
        A[K], B[K] = sim_phase(K, 100), sim_phase(K, 1)
        print(f"  {K:>3} {A[K]:>14.1f} {(A[K]/A[1]-1)*100:>9.2f}%   "
              f"{B[K]:>13.1f} {(B[K]/B[1]-1)*100:>9.2f}%")
    print(f"\n  ⇒ 相位A最优 K={min(A, key=A.get)}；相位B最优 K={min(B, key=B.get)}")

    # DP oracle
    AMAX = 80
    INF = float("inf")
    V = [[INF] * (AMAX + 1) for _ in range(T_MAX + 1)]
    ACT = [[1] * (AMAX + 1) for _ in range(T_MAX + 1)]
    for a in range(AMAX + 1):
        V[T_MAX][a] = 0.0
    for t in range(T_MAX - 1, -1, -1):
        for a in range(AMAX + 1):
            cr = r0 + Nfn(t, 0) + V[t + 1][0]
            ck = Nfn(t, a) + V[t + 1][a + 1] if a < AMAX else INF
            if cr <= ck:
                V[t][a], ACT[t][a] = cr, 1
            else:
                V[t][a], ACT[t][a] = ck, 0
    tot, a, nr, path = 0.0, 0, 0, []
    for t in range(T_MAX):
        if ACT[t][a] == 1:
            tot += r0 + Nfn(t + 1, 0)
            nr += 1
            a = 0
            path.append(t + 1)
        else:
            tot += Nfn(t + 1, a)
            a += 1
    gaps = [y - x for x, y in zip(path, path[1:])]
    print(f"\n  P5 oracle：{tot:.1f}（重建 {nr} 次，间隔中位 {st.median(gaps):.0f}）"
          f"，相对 P1 {(tot/base-1)*100:+.2f}%")

    # 在线
    def sim_online(predict, warm=100, amax=80):
        t_, a, nr, hist = 0.0, 0, 0, []
        for t in range(1, T_MAX + 1):
            if t <= warm:
                t_ += r0 + Nfn(t, 0)
                nr += 1
                a = 1
                hist.append(Nfn(t, 0))
                continue
            avg = t_ / (t - 1)
            pred = predict(hist, a)
            if a >= amax or pred >= avg:
                t_ += r0 + Nfn(t, 0)
                nr += 1
                a = 1
                hist.append(Nfn(t, 0))
            else:
                t_ += Nfn(t, a)
                a += 1
                hist.append(Nfn(t, a))
        return t_, nr

    def p_last(h, a):
        return h[-1]

    def p_slope(h, a):
        w = h[-11:] if len(h) >= 11 else h
        if len(w) < 5:
            return h[-1]
        s = (w[-1] - w[0]) / max(1, len(w) - 1)
        return max(1.0, w[-1] + s * max(1, a))

    print(f"\n  {'策略':>24} {'代价':>10} {'重建':>6} {'相对P1':>9} {'Regret':>9}")
    print(f"  {'P1 每步重建':>24} {base:>10.1f} {344:>6} {'0.00%':>9} "
          f"{(base/tot-1)*100:>8.2f}%")
    for name, pf in [("P4a 上一值", p_last), ("P4c 年龄斜率", p_slope)]:
        c, nrb = sim_online(pf)
        print(f"  {name:>24} {c:>10.1f} {nrb:>6} {(c/base-1)*100:>8.2f}% "
              f"{(c/tot-1)*100:>8.2f}%")
    print(f"  {'P5 oracle（不可实现）':>24} {tot:>10.1f} {nr:>6} "
          f"{(tot/base-1)*100:>8.2f}% {0.0:>8.2f}%")

    # ── 6. 与 L2 对照 ──
    print(f"\n{'='*100}")
    print("4. ★ 与 levels=2 的对照")
    print(f"{'='*100}")
    print(f"  {'量':>26} {'levels=2':>12} {'levels=5':>12}")
    print(f"  {'r':>26} {22.43:>12.2f} {r0:>12.2f}")
    print(f"  {'ΔN_step(1) 中位':>26} {21.0:>12.1f} "
          f"{st.median([st.median(a1[t]) - a0[t] for t in common]):>12.1f}")
    print(f"  {'门限 r > ΔN_step(1)':>26} "
          f"{'临界' if 22.43 > 21 else '未过':>12} "
          f"{'✓ 越过' if r0 > st.median([st.median(a1[t]) - a0[t] for t in common]) else '未过':>12}")
    print(f"  {'oracle 收益 vs P1':>26} {-13.31:>11.2f}% {(tot/base-1)*100:>11.2f}%")

    with open("l5_result.json", "w") as f:
        json.dump(dict(r=r0, real={str(k): v for k, v in real.items()},
                       A={str(k): v for k, v in A.items()},
                       B={str(k): v for k, v in B.items()},
                       oracle=tot, oracle_path=path, base=base), f, indent=1)
    print("\n⇒ 写入 l5_result.json")


if __name__ == "__main__":
    main()
