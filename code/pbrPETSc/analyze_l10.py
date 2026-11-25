#!/usr/bin/env python3
"""
★★★ levels=10 完整分析（与 L2/L5 同口径，便于横向对比）

检验目标：r 从 35（L5）升到 58（L10）是否继续放大决策空间与收益，或已饱和。

关键判据回顾：
    复用胜出 ⟺ ΔN_step(a) < r          （ΔN_step = 每步 s 次求解的总劣化）
    每步 s = 3 次求解 ⇒ 等价于 ΔN_single < r/3
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
        if TIME_RE.match(ln):
            if cur is not None:
                steps.append(cur)
            cur = dict(reused=None, b=None, solves=[])
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
                        r=r["tPCSetup"] / r["tIter"]))
    return out


def main():
    print("=" * 100)
    print("★★★ levels=10 完整分析")
    print("=" * 100)

    l10 = {}
    for K in (1, 2, 3, 4, 5, 6, 8):
        runs = [load_run(f"l10/log.k{K}r{R}", f"l10_k{K}_r{R}.csv")
                for R in (1, 2, 3)]
        runs = [x for x in runs if x]
        if runs:
            l10[K] = runs
    bigs = [load_run(f"l10/log.big{R}", f"l10_big_r{R}.csv") for R in (1, 2)]
    bigs = [b for b in bigs if b]

    if not l10:
        print("  L10 数据尚未就绪")
        return
    print(f"\n  载入 K ∈ {sorted(l10)}，大年龄 {len(bigs)} 份")

    # r
    rs = [d["r"] for K, runs in l10.items() for run in runs for d in run
          if d["reused"] == 0 and d["r"] > 0]
    r0 = st.median(rs)
    print(f"  ★ r = {r0:.2f}（n={len(rs)}）")

    # 年龄曲线
    cells = defaultdict(list)
    for K, runs in l10.items():
        for run in runs:
            for d in run:
                cells[(d["t"], d["t"] - d["b"])].append(d["Nsum"])
    for run in bigs:
        for d in run:
            cells[(d["t"], d["t"] - d["b"])].append(d["Nsum"])
    tab = {k: st.median(v) for k, v in cells.items()}
    bya = defaultdict(list)
    for (t, a), v in tab.items():
        bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amax_obs = max(curve)

    def Nfn(t, a):
        if (t, a) in tab:
            return tab[(t, a)]
        same = [(abs(aa - a), v) for (tt, aa), v in tab.items() if tt == t]
        if same:
            return min(same)[1]
        if a in curve:
            return curve[a]
        return curve[amax_obs]

    print(f"\n  表：{len(tab)} 格，a ∈ [0, {amax_obs}]")
    print(f"\n  年龄曲线 N_step(a)（a=0..12）:")
    print("    " + " ".join(f"{curve.get(a, 0):.0f}" for a in range(13)))
    print(f"\n  {'a':>3} {'N_step':>9} {'dN':>8} {'vs r':>9} {'判定':>6}")
    for a in range(0, 13):
        if a not in curve:
            continue
        dn = curve[a] - curve[0]
        f = "-" if a == 0 else ("reuse" if dn < r0 else "REBUILD")
        print(f"  {a:>3} {curve[a]:>9.1f} {dn:>8.1f} {dn-r0:>+9.1f} {f:>6}")

    # 时间分辨判据
    print(f"\n{'='*100}")
    print("1. 判据的时间分辨形态（r = %.1f）" % r0)
    print(f"{'='*100}")
    a0 = {t: tab[(t, 0)] for (t, a) in tab if a == 0}
    a1 = defaultdict(list)
    for (t, a), v in tab.items():
        if a == 1:
            a1[t].append(v)
    common = sorted(set(a0) & set(a1))
    print(f"  {'步段':>12} {'dN(0->1) 中位':>14} {'样本':>6} {'判定':>8}")
    for lo, hi in ((101, 150), (151, 200), (201, 250), (251, 300), (301, 344)):
        ds = [st.median(a1[t]) - a0[t] for t in common if lo <= t <= hi]
        if ds:
            m = st.median(ds)
            print(f"  {f'{lo}-{hi}':>12} {m:>14.1f} {len(ds):>6} "
                  f"{'reuse' if m < r0 else 'REBUILD':>8}")

    # 实测代价
    print(f"\n{'='*100}")
    print("2. 实测代价（无相位歧义口径）")
    print(f"{'='*100}")
    print(f"  {'K':>3} {'重建数':>7} {'Sr':>10} {'SN':>9} {'cost':>10} "
          f"{'相对K=1':>10} {'SN三次极差':>12}")
    real = {}
    for K in sorted(l10):
        cs, srs, sns, nrs = [], [], [], []
        for run in l10[K]:
            sr = sum(d["r"] for d in run if d["r"])
            sn = sum(d["Nsum"] for d in run)
            srs.append(sr)
            sns.append(sn)
            cs.append(sr + sn)
            nrs.append(sum(1 for d in run if d["reused"] == 0))
        real[K] = st.median(cs)
        rel = ""
        if 1 in real:
            rel = "%+9.2f%%" % ((st.median(cs) / real[1] - 1) * 100)
        print(f"  {K:>3} {st.median(nrs):>7.0f} {st.median(srs):>10.1f} "
              f"{st.median(sns):>9.0f} {st.median(cs):>10.1f} {rel:>10} "
              f"{max(sns)-min(sns):>12}")
    bestK = min(real, key=real.get)
    print(f"\n  => 实测最优 K* = {bestK} "
          f"（相对 K=1 {(real[bestK]/real[1]-1)*100:+.2f}%）")

    # 相位扫描
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

    print(f"\n  相位 A（b0=100，与真实运行一致）:")
    A = {K: sim_phase(K, 100) for K in range(1, 13)}
    for K in range(1, 13):
        print(f"    K={K:>2}: {A[K]:>10.1f}  {(A[K]/A[1]-1)*100:>+8.2f}%")
    print(f"  => 相位A最优 K={min(A, key=A.get)}")

    # oracle
    print(f"\n{'='*100}")
    print("3. 真 oracle 与在线策略")
    print(f"{'='*100}")
    AMAX = 90
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
    print(f"  oracle: cost={tot:.1f}, 重建 {nr} 次, "
          f"间隔中位 {st.median(gaps):.0f} [{min(gaps)}, {max(gaps)}]")

    base = sim_phase(1, 100)

    def sim_v4(Nfn, r0, b0=100, amax=80, lvl_mode="last", avg_mode="recent"):
        know = defaultdict(list)
        levels = []
        t_, a, acc, accn = 0.0, 0, 0.0, 0
        for t in range(1, T_MAX + 1):
            lvl = levels[-1] if levels else None
            if t < b0:
                rebuild = True
            elif a == 0 or a >= amax:
                rebuild = True
            else:
                avg = acc / accn if accn else t_ / (t - 1)
                if lvl is None:
                    est = 45.0 * a
                else:
                    if a in know and know[a]:
                        delta = st.median(know[a])
                    elif know:
                        ks = sorted(k for k in know if know[k])
                        if len(ks) >= 2:
                            a2, a1 = ks[-1], ks[-2]
                            d2 = st.median(know[a2])
                            d1 = st.median(know[a1])
                            sl = (d2 - d1) / max(1e-9, a2 - a1)
                            delta = d2 + sl * (a - a2)
                        else:
                            delta = st.median(know[ks[-1]])
                    else:
                        delta = 0.0
                    est = lvl + max(0.0, delta)
                rebuild = est > avg
            if rebuild:
                nn = Nfn(t, 0)
                t_ += r0 + nn
                acc, accn = r0 + nn, 1
                a = 1
                levels.append(nn)
            else:
                nn = Nfn(t, a)
                t_ += nn
                acc += nn
                accn += 1
                if levels:
                    bmed = st.median(levels)
                    if bmed > 1e-9:
                        know[a].append(nn - bmed)
                a += 1
        return t_

    # ceiling（真 N(t,a) + avg_recent 判据）
    def sim_ceiling(Nfn, r0, b0=100, amax=80):
        t_, a, acc, accn = 0.0, 0, 0.0, 0
        for t in range(1, T_MAX + 1):
            if t < b0:
                v = r0 + Nfn(t, 0)
                t_ += v
                acc, accn = v, 1
                a = 1
                continue
            avg = acc / accn if accn else t_ / (t - 1)
            if a == 0 or a >= amax or Nfn(t, a) > avg:
                v = r0 + Nfn(t, 0)
                t_ += v
                acc, accn = v, 1
                a = 1
            else:
                v = Nfn(t, a)
                t_ += v
                acc += v
                accn += 1
                a += 1
        return t_

    cv = sim_ceiling(Nfn, r0)
    on = sim_v4(Nfn, r0)
    print(f"\n  {'策略':>40} {'cost':>10} {'相对K=1':>9} {'Regret':>9}")
    print(f"  {'K=1 每步重建':>40} {base:>10.1f} {0.0:>8.2f}% "
          f"{(base/tot-1)*100:>8.2f}%")
    print(f"  {f'K*={bestK} 离线最优固定周期':>40} {real[bestK]:>10.1f} "
          f"{(real[bestK]/base-1)*100:>8.2f}% {(real[bestK]/tot-1)*100:>8.2f}%")
    print(f"  {'C0 ceiling（真N(t,a)+avg_recent）':>40} {cv:>10.1f} "
          f"{(cv/base-1)*100:>8.2f}% {(cv/tot-1)*100:>8.2f}%")
    print(f"  {'v4 在线（lvl=last + avg_recent）':>40} {on:>10.1f} "
          f"{(on/base-1)*100:>8.2f}% {(on/tot-1)*100:>8.2f}%")
    print(f"  {'真 oracle':>40} {tot:>10.1f} "
          f"{(tot/base-1)*100:>8.2f}% {0.0:>8.2f}%")

    # 跨 levels 汇总
    print(f"\n{'='*100}")
    print("4. 跨 levels 汇总")
    print(f"{'='*100}")
    print(f"  {'levels':>7} {'r':>8} {'K*':>4} {'K=1':>9} {'固定周期':>9} "
          f"{'在线v4':>9} {'oracle':>9}")
    for lv, rr_, kstar, ra, rce, ron, ror in [
            (2, 22.43, 1, 13.60, -1, 13.61, 11.97),
            (5, 35.00, 2, 39.12, 27.43, 21.78, 28.12),
            (10, r0, bestK, (base/tot-1)*100, (real[bestK]/tot-1)*100,
             (on/tot-1)*100, (tot/base-1)*100)]:
        print(f"  {lv:>7} {rr_:>8.2f} {kstar:>4} {ra:>8.2f}% {rce:>8.2f}% "
              f"{ron:>8.2f}% {ror:>8.2f}%")
    print("  （表中除 r 外均为 regret，相对各自 oracle；oracle 列为其相对 K=1 的收益）")

    with open("l10_result.json", "w") as f:
        json.dump(dict(r=r0, real={str(k): v for k, v in real.items()},
                       bestK=bestK, oracle=tot, ceiling=cv, online=on,
                       curve={str(k): v for k, v in curve.items()}), f, indent=1)
    print("\n=> 写入 l10_result.json")


if __name__ == "__main__":
    main()
