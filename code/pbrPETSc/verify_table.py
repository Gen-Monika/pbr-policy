#!/usr/bin/env python3
"""
★ 可信度检验：表格模拟能否复现真实运行的实测代价？

═══════════════════════════════════════════════════════════════════════
要检验的疑点
═══════════════════════════════════════════════════════════════════════
真实运行的实测（sum 口径）：
    K=1: Σr=7622.8  ΣN=30740  ⇒ cost=38362.8
    K=2: Σr=5023.6  ΣN=33591  ⇒ cost=38614.6   (+0.66%，比 K=1 差)

但表格模拟给出 K=2 = 35865.8 (-6.59%，比 K=1 好)。
两者矛盾。

疑似原因：固定周期策略有【相位】参数。
    真实运行：b0 = 100 ⇒ 重建发生在 t = 100, 100+K, 100+2K, ...
    我的模拟：a 从 0 开始 ⇒ 重建发生在 t = 1, 1+K, 1+2K, ...
在漂移非平稳（判据在第 150 步翻转）时，相位不同 ⇒ 结果不同。

═══════════════════════════════════════════════════════════════════════
检验方法
═══════════════════════════════════════════════════════════════════════
用表格 N(t,a) 精确【重放】每个真实运行的 (t,b) 决策序列，
比较重放出的 ΣN 与实测 ΣN。
  一致 ⇒ 表格忠实，在线策略的 regret 可信
  不一致 ⇒ 表格有偏，需查原因

同时报告：重放过程中有多少步落在【实测格子】上，多少步依赖回退插值。
"""
import os
import re
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


def load_run(K):
    if K == "big":
        logp, csvp, reps = "sbig/log.big1", "sbig_r1.csv", None
        steps, rows = parse_log(logp), load_csv(csvp)
        n = min(len(steps), len(rows))
        return [dict(t=i + 1, b=steps[i]["b"] or (i + 1), reused=steps[i]["reused"],
                     Nsum=sum(steps[i]["solves"]),
                     r=rows[i]["tPCSetup"] / rows[i]["tIter"]
                     if rows[i]["tIter"] > 0 else None)
                for i in range(n)]
    steps, rows = parse_log(f"s{K}/log.s1"), load_csv(f"s_k{K}_r1.csv")
    n = min(len(steps), len(rows))
    return [dict(t=i + 1, b=steps[i]["b"] or (i + 1), reused=steps[i]["reused"],
                 Nsum=sum(steps[i]["solves"]),
                 r=rows[i]["tPCSetup"] / rows[i]["tIter"] if rows[i]["tIter"] > 0 else None)
            for i in range(n)]


def main():
    print("=" * 100)
    print("★ 表格忠实度检验：能否重放真实运行的决策序列？")
    print("=" * 100)

    # 建表：只用【非本运行】的样本？不——先做"留一"更严格。
    # 这里先用全体样本建表，看能否复现。
    datasets = [(f"s{K}/log.s{rep}", f"s_k{K}_r{rep}.csv")
                for K in (1, 2, 3, 4, 5, 6, 8) for rep in (1, 2, 3)]
    datasets += [(f"sbig/log.big{rep}", f"sbig_r{rep}.csv") for rep in (1, 2, 3)]

    cells = defaultdict(list)
    rs = []
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
    tab = {k: st.median(v) for k, v in cells.items()}
    r0 = st.median(rs)

    def Nfn(t, a, exclude=None):
        """返回 (值, 是否命中实测格子)。exclude=(K_标签) 用于留一。"""
        if (t, a) in tab:
            return tab[(t, a)], True
        same_t = [(abs(aa - a), v) for (tt, aa), v in tab.items() if tt == t]
        if same_t:
            return min(same_t)[1], False
        bya = [v for (tt, aa), v in tab.items() if aa == a]
        if bya:
            return st.median(bya), False
        return st.median(list(tab.values())), False

    print(f"\n  表：{len(tab)} 格，r0 = {r0:.3f}")

    print(f"\n  {'K':>5} {'实测ΣN':>9} {'重放ΣN':>9} {'偏差':>9} {'偏差%':>9} "
          f"{'命中实测格':>11} {'回退插值':>9}")
    for K in (1, 2, 3, 4, 5, 6, 8, "big"):
        run = load_run(K)
        if not run:
            continue
        real = sum(d["Nsum"] for d in run)
        rep, hit, miss = 0, 0, 0
        for d in run:
            v, ok = Nfn(d["t"], d["t"] - d["b"])
            rep += v
            hit += ok
            miss += (not ok)
        print(f"  {str(K):>5} {real:>9} {rep:>9.0f} {rep-real:>+9.0f} "
              f"{(rep/real-1)*100:>8.2f}% {hit:>11} {miss:>9}")

    # ── 相位检验 ──
    print(f"\n{'='*100}")
    print("2. ★ 相位检验：真实运行的重建相位 vs 我的模拟相位")
    print(f"{'='*100}")
    for K in (2, 3, 5):
        run = load_run(K)
        rebs = [d["t"] for d in run if d["reused"] == 0]
        post = [t for t in rebs if t >= 100]
        print(f"\n  K={K}: 重建共 {len(rebs)} 次（含 t<100 的 {len(rebs)-len(post)} 次）")
        print(f"    t>=100 的重建时刻（前 10）: {post[:10]}")
        # 我的模拟相位：从 t=1 起，每 K 步
        simphase = list(range(1, 21, K))
        print(f"    模拟相位（前 10）        : {simphase}")

    # ── 相位对齐后的 K 扫描 ──
    print(f"\n{'='*100}")
    print("3. ★ 相位对齐的固定周期扫描（两种相位并列）")
    print(f"{'='*100}")
    print("  相位 A：与真实运行一致（b0=100，t<100 每步重建）")
    print("  相位 B：从 t=1 起每 K 步（我先前误用的相位）")

    def sim_phase(K, b0):
        tot, a, nr = 0.0, 0, 0
        for t in range(1, T_MAX + 1):
            rebuild = (t < b0) or (t >= b0 and (t - b0) % K == 0)
            if rebuild:
                tot += r0 + Nfn(t, 0)[0]
                nr += 1
                a = 1
            else:
                tot += Nfn(t, a)[0]
                a += 1
        return tot, nr

    print(f"\n  {'K':>3} {'相位A代价':>11} {'重建':>6} {'相对K=1':>10}   "
          f"{'相位B代价':>11} {'相对K=1':>10}")
    A, B = {}, {}
    for K in range(1, 13):
        ca, na = sim_phase(K, 100)
        cb, nb = sim_phase(K, 1)
        A[K], B[K] = ca, cb
        print(f"  {K:>3} {ca:>11.1f} {na:>6} {(ca/A[1]-1)*100:>9.2f}%   "
              f"{cb:>11.1f} {(cb/B[1]-1)*100:>9.2f}%")
    print(f"\n  ⇒ 相位A最优 K={min(A, key=A.get)}；相位B最优 K={min(B, key=B.get)}")

    # ── 真实运行的实测代价（无相位歧义） ──
    print(f"\n{'='*100}")
    print("4. ★ 真实运行的实测代价（唯一无歧义的口径）")
    print(f"{'='*100}")
    print(f"  {'K':>3} {'重建数':>7} {'Σr':>9} {'ΣN(实测)':>10} {'cost':>10} {'相对K=1':>10}")
    real = {}
    for K in (1, 2, 3, 4, 5, 6, 8):
        run = load_run(K)
        sr = sum(d["r"] for d in run if d["r"])
        sn = sum(d["Nsum"] for d in run)
        nreb = sum(1 for d in run if d["reused"] == 0)
        real[K] = sr + sn
        rel = f"{(real[K]/real[1]-1)*100:+9.2f}%" if 1 in real else ""
        print(f"  {K:>3} {nreb:>7} {sr:>9.1f} {sn:>10} {real[K]:>10.1f} {rel:>10}")
    print(f"\n  ⇒ 实测最优 K = {min(real, key=real.get)}")


if __name__ == "__main__":
    main()
