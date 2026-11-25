#!/usr/bin/env python3
"""
★★ 相位效应的正确利用：既然判据在第 150 步翻转，最优策略应"分段"。

═══════════════════════════════════════════════════════════════════════
已确立的事实（verify_table.py 已验证表格可精确重放，偏差 ≤ 5）
═══════════════════════════════════════════════════════════════════════
1. 固定周期策略有【相位】：b0=100 与 b0=1 给出不同结论。
   真实运行用 b0=100 ⇒ 实测最优 K=1。
2. ΔN_step(0→1) 在步段 101–150 是 38（> r=22.3），151 之后降到 16–22（≤ r）。
   ⇒ 判据在第 150 步前后【翻转】。
3. 表格忠实 ⇒ 可以可靠地评估"分段策略"。

═══════════════════════════════════════════════════════════════════════
本脚本评估的策略族
═══════════════════════════════════════════════════════════════════════
  P1  每步重建（K=1）                          —— 默认做法
  P2  固定周期 K（b0=100，与真实运行一致的相位）
  P3  ★ 延迟启动：t < τ 每步重建，之后每 K 步   —— 利用判据翻转
  P4  ★★ 在线：判据驱动，阈值由历史估计
  P5  DP oracle（上界）
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


def build_table():
    datasets = [(f"s{K}/log.s{rep}", f"s_k{K}_r{rep}.csv")
                for K in (1, 2, 3, 4, 5, 6, 8) for rep in (1, 2, 3)]
    datasets += [(f"sbig/log.big{rep}", f"sbig_r{rep}.csv") for rep in (1, 2, 3)]
    cells, rs = defaultdict(list), []
    for logp, csvp in datasets:
        if not (os.path.exists(logp) and os.path.exists(csvp)):
            continue
        steps, rows = parse_log(logp), load_csv(csvp)
        for i in range(min(len(steps), len(rows))):
            s, r = steps[i], rows[i]
            if r["tIter"] <= 0:
                continue
            t, b = i + 1, (s["b"] or (i + 1))
            cells[(t, t - b)].append(sum(s["solves"]))
            if s["reused"] == 0:
                rs.append(r["tPCSetup"] / r["tIter"])
    return {k: st.median(v) for k, v in cells.items()}, st.median(rs)


TAB, R0 = build_table()


def Nfn(t, a):
    if (t, a) in TAB:
        return TAB[(t, a)]
    same_t = [(abs(aa - a), v) for (tt, aa), v in TAB.items() if tt == t]
    if same_t:
        return min(same_t)[1]
    bya = [v for (tt, aa), v in TAB.items() if aa == a]
    if bya:
        return st.median(bya)
    return st.median(list(TAB.values()))


def main():
    print("=" * 100)
    print("★ 分段策略与在线策略（相位已对齐真实运行：t<100 每步重建）")
    print("=" * 100)
    print(f"\n  r0 = {R0:.3f}，表格 {len(TAB)} 格")

    # 参照：每步重建
    def sim_always():
        tot = 0.0
        for t in range(1, T_MAX + 1):
            tot += R0 + Nfn(t, 0)
        return tot
    base = sim_always()
    print(f"  P1 每步重建：{base:.1f}")

    # ── P3 延迟启动 ──
    print(f"\n{'='*100}")
    print("P3 ★ 延迟启动：t < τ 每步重建，之后每 K 步重建一次")
    print(f"{'='*100}")
    best = (None, None, float("inf"))
    print(f"  {'τ':>5} " + "".join(f"{'K='+str(K):>10}" for K in (2, 3, 4, 5, 6, 8)))
    for tau in (100, 120, 140, 150, 160, 180, 200, 220, 240):
        line = f"  {tau:>5} "
        for K in (2, 3, 4, 5, 6, 8):
            tot, a, nr = 0.0, 0, 0
            for t in range(1, T_MAX + 1):
                if t < tau:
                    rebuild = True
                else:
                    rebuild = ((t - tau) % K == 0)
                if rebuild:
                    tot += R0 + Nfn(t, 0)
                    nr += 1
                    a = 1
                else:
                    tot += Nfn(t, a)
                    a += 1
            line += f"{tot:>10.1f}"
            if tot < best[2]:
                best = (tau, K, tot)
        print(line)
    print(f"\n  ⇒ P3 最优：τ={best[0]}, K={best[1]}，代价 {best[2]:.1f} "
          f"（相对 P1 {(best[2]/base-1)*100:+.2f}%）")

    # ── P4 在线：判据驱动 ──
    print(f"\n{'='*100}")
    print("P4 ★★ 在线：判据驱动的自适应重建")
    print(f"{'='*100}")
    print("  规则：维护『每步平均代价』avg；若预测下一步 N > avg 则重建")
    print("  预测器用近期观测的①上一值 ②近窗中位 ③年龄斜率外推")

    def sim_online(predict, warm=100, amax=80):
        tot, a, nr, hist = 0.0, 0, 0, []
        for t in range(1, T_MAX + 1):
            if t <= warm:
                tot += R0 + Nfn(t, 0)
                nr += 1
                a = 1
                hist.append(Nfn(t, 0))
                continue
            avg = tot / (t - 1)
            pred = predict(hist, a)
            if a >= amax or pred >= avg:
                tot += R0 + Nfn(t, 0)
                nr += 1
                a = 1
                hist.append(Nfn(t, 0))
            else:
                tot += Nfn(t, a)
                a += 1
                hist.append(Nfn(t, a))
        return tot, nr

    def p_last(h, a):
        return h[-1]

    def p_med(h, a):
        w = h[-11:] if len(h) >= 11 else h
        return st.median(w)

    def p_slope(h, a):
        w = h[-11:] if len(h) >= 11 else h
        if len(w) < 5:
            return h[-1]
        s = (w[-1] - w[0]) / max(1, len(w) - 1)
        return max(1.0, w[-1] + s * max(1, a))

    def p_slope_strong(h, a):
        w = h[-11:] if len(h) >= 11 else h
        if len(w) < 5:
            return h[-1]
        s = (w[-1] - w[0]) / max(1, len(w) - 1)
        return max(1.0, w[-1] + 2.0 * s * max(1, a))

    # ── P5 oracle ──
    def sim_dp(AMAX=80):
        INF = float("inf")
        V = [[INF] * (AMAX + 1) for _ in range(T_MAX + 1)]
        A_ = [[1] * (AMAX + 1) for _ in range(T_MAX + 1)]
        for a in range(AMAX + 1):
            V[T_MAX][a] = 0.0
        for t in range(T_MAX - 1, -1, -1):
            for a in range(AMAX + 1):
                cr = R0 + Nfn(t, 0) + V[t + 1][0]
                ck = Nfn(t, a) + V[t + 1][a + 1] if a < AMAX else INF
                if cr <= ck:
                    V[t][a], A_[t][a] = cr, 1
                else:
                    V[t][a], A_[t][a] = ck, 0
        tot, a, nr, path = 0.0, 0, 0, []
        for t in range(T_MAX):
            if A_[t][a] == 1:
                tot += R0 + Nfn(t + 1, 0)
                nr += 1
                a = 0
                path.append(t + 1)
            else:
                tot += Nfn(t + 1, a)
                a += 1
        return tot, nr, path

    orc, orcnr, orcpath = sim_dp()
    print(f"\n  P5 oracle：{orc:.1f}（重建 {orcnr} 次）")
    gaps = [y - x for x, y in zip(orcpath, orcpath[1:])]
    print(f"     重建时刻（前 20）: {orcpath[:20]}")
    print(f"     间隔：中位 {st.median(gaps):.0f}，范围 [{min(gaps)}, {max(gaps)}]")

    print(f"\n  {'策略':>26} {'代价':>10} {'重建':>6} {'相对P1':>9} {'Regret':>9}")
    print(f"  {'P1 每步重建':>26} {base:>10.1f} {344:>6} {0.0:>8.2f}% "
          f"{(base/orc-1)*100:>8.2f}%")
    print(f"  {'P3 延迟启动 (τ=%d,K=%d)' % best[:2]:>26} {best[2]:>10.1f} "
          f"{'—':>6} {(best[2]/base-1)*100:>8.2f}% {(best[2]/orc-1)*100:>8.2f}%")
    onres = {}
    for name, pf in [("P4a 上一值", p_last), ("P4b 近窗中位", p_med),
                     ("P4c 年龄斜率", p_slope), ("P4d 斜率×2", p_slope_strong)]:
        c, nr = sim_online(pf)
        onres[name] = c
        print(f"  {name:>26} {c:>10.1f} {nr:>6} {(c/base-1)*100:>8.2f}% "
              f"{(c/orc-1)*100:>8.2f}%")
    print(f"  {'P5 oracle（不可实现）':>26} {orc:>10.1f} {orcnr:>6} "
          f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")

    with open("phase_result.json", "w") as f:
        json.dump(dict(r=R0, base=base, best_tau_k=best[:2], best_cost=best[2],
                       oracle=orc, oracle_path=orcpath, online=onres), f, indent=1)
    print("\n⇒ 写入 phase_result.json")


if __name__ == "__main__":
    main()
