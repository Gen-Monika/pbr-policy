#!/usr/bin/env python3
"""
★ 修正版完整分析（取代 analyze_k.py 与 online_policy.py 的 N 相关部分）

═══════════════════════════════════════════════════════════════════════
被修正的错误
═══════════════════════════════════════════════════════════════════════
旧 load_N() 抓取全部 "Solving for p_rgh" 行（1032 条 = 3 × 344），
而 CSV 只有 344 行（1 行/步）。旧代码 min(344, 1032) 截断，
⇒ 用前 ~115 步的迭代数冒充全部 344 步。所有 N 相关结论作废。

═══════════════════════════════════════════════════════════════════════
正确的日志结构（逐行核对确认）
═══════════════════════════════════════════════════════════════════════
    Time = <t>                                    ← 1 个时间步
    PIMPLE: iteration 1
    smoothSolver:  Solving for alpha.water ...
    PETSc ilu lvl=2 rebuild|REUSE@b : t_pcsetup=.. r=..   ← 1 次预条件子构造
    PETScILUPCG:  Solving for p_rgh ... No Iterations 32  ┐
    PETScILUPCG:  Solving for p_rgh ... No Iterations 6   ├ 3 次压力求解
    PETScILUPCG:  Solving for p_rgh ... No Iterations 0   ┘
    smoothSolver:  Solving for epsilon ...
    smoothSolver:  Solving for k ...
    Time = <t'>                                   ← 下一步

⇒ 每步恰好 1 次构造 + 3 次求解（实测分布 {3: 344}）

═══════════════════════════════════════════════════════════════════════
两种口径（结论对口径敏感，必须判定）
═══════════════════════════════════════════════════════════════════════
  first : 只数每步第 1 次求解
  sum   : 数每步 3 次求解之和  ← ★ 物理正确：同一次构造服务 3 次求解，
                                  3 次迭代代价都要付

  ⇒ 若 1 次构造服务 3 次求解，则每步代价 = t_pcsetup + (N1+N2+N3)·t_iter
    ⇒ sum 口径正确。本脚本两种都算，并明确对比。

═══════════════════════════════════════════════════════════════════════
无量纲化
═══════════════════════════════════════════════════════════════════════
  cost(K) = Σ_t [ r(t) + N(t) ]        [单位：一次 CG 迭代]

      r(t) = t_pcsetup(t)/t_iter(t)   ← 同一步内取值，消除机器状态漂移
"""
import os
import re
import statistics as st
from collections import defaultdict

CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
REUSE_RE = re.compile(r"REUSE@(\d+)")


def parse_log(path):
    """每步一条记录：{t, reused, b, solves:[...]}"""
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
        cols = CSV_HDR if len(p) == 20 else (CSV_HDR[:11] + CSV_HDR[12:] if len(p) == 19 else None)
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


def load_run(K, rep=1):
    steps = parse_log(f"s{K}/log.s{rep}")
    rows = load_csv(f"s_k{K}_r{rep}.csv")
    n = min(len(steps), len(rows))
    out = []
    for i in range(n):
        s, r = steps[i], rows[i]
        if r["tIter"] <= 0:
            continue
        out.append(dict(
            t=i + 1, b=s["b"] or (i + 1), reused=s["reused"],
            solves=s["solves"], Nfirst=s["solves"][0] if s["solves"] else 0,
            Nsum=sum(s["solves"]),
            tsetup=r["tPCSetup"], titer=r["tIter"],
            r=r["tPCSetup"] / r["tIter"],
        ))
    return out


def cost(run, mode="sum"):
    """返回 (cost_iter_equiv, Σr, ΣN)"""
    sr = sum(d["r"] for d in run)
    sn = sum(d["Nfirst"] if mode == "first" else d["Nsum"] for d in run)
    return sr + sn, sr, sn


def main():
    print("=" * 100)
    print("★ 修正版分析：正确配对日志与 CSV")
    print("=" * 100)

    runs = {}
    for K in (1, 2, 3, 4, 5, 6, 8):
        r = load_run(K)
        if r:
            runs[K] = r
    print(f"\n载入 {len(runs)} 个 K 的运行，各 {len(list(runs.values())[0])} 步")

    # ── 结构验证 ──
    print(f"\n{'='*100}")
    print("1. 结构验证（每步求解次数、构造次数）")
    print(f"{'='*100}")
    print(f"  {'K':>3} {'步数':>5} {'每步求解数':>12} {'构造次数':>8} {'复用次数':>8}")
    for K, run in sorted(runs.items()):
        ns = [len(d["solves"]) for d in run]
        print(f"  {K:>3} {len(run):>5} {str(sorted(set(ns))):>12} "
              f"{sum(1 for d in run if d['reused']==0):>8} "
              f"{sum(1 for d in run if d['reused']==1):>8}")

    # ── 两种口径的 K 扫描 ──
    print(f"\n{'='*100}")
    print("2. ★ 成本模型 K 扫描（两种口径并列，暴露口径敏感性）")
    print(f"{'='*100}")
    print(f"  {'K':>3} {'重建数':>7} {'Σr':>9} "
          f"{'ΣN(first)':>11} {'cost(first)':>12} {'相对':>9}   "
          f"{'ΣN(sum)':>10} {'cost(sum)':>11} {'相对':>9}")
    cf, cs = {}, {}
    for K in sorted(runs):
        run = runs[K]
        nreb = sum(1 for d in run if d["reused"] == 0)
        c1, sr, sn1 = cost(run, "first")
        c2, _, sn2 = cost(run, "sum")
        cf[K], cs[K] = c1, c2
        r1 = f"{(c1/cf[1]-1)*100:+8.2f}%" if 1 in cf else ""
        r2 = f"{(c2/cs[1]-1)*100:+8.2f}%" if 1 in cs else ""
        print(f"  {K:>3} {nreb:>7} {sr:>9.1f} {sn1:>11} {c1:>12.1f} {r1:>9}   "
              f"{sn2:>10} {c2:>11.1f} {r2:>9}")

    bf = min(cf, key=cf.get)
    bs = min(cs, key=cs.get)
    print(f"\n  ⇒ first 口径最优 K = {bf}（cost {cf[bf]:.1f}，"
          f"相对 K=1 {(cf[bf]/cf[1]-1)*100:+.2f}%）")
    print(f"  ⇒ sum   口径最优 K = {bs}（cost {cs[bs]:.1f}，"
          f"相对 K=1 {(cs[bs]/cs[1]-1)*100:+.2f}%）")
    print(f"\n  ⚠️ 两者结论{'一致' if bf == bs else '不同'}。")
    print(f"     r 以【一次 CG 迭代】为单位，而每步有 3 次求解：")
    print(f"     重建成本 r ≈ 22，每步总迭代数 ≈ {st.median([d['Nsum'] for d in runs[1]]):.0f}")
    print(f"     ⇒ 判据为「每步总劣化 ΔN_step 是否 < r」")
    print(f"     ⇒ 若 1 次构造服务 3 次求解，则 ΔN_step 是单次求解劣化的 3 倍，")
    print(f"        决策空间比按单次求解估计时【窄得多】。")

    # ── 单步劣化 ──
    print(f"\n{'='*100}")
    print("3. ★ 每步总劣化 ΔN_step（决定判据是否成立）")
    print(f"{'='*100}")
    for K in (2, 3, 5, 8):
        if K not in runs:
            continue
        run = runs[K]
        print(f"\n  K={K}: 冻结点附近逐步展开")
        print(f"    {'步':>4} {'b':>5} {'年龄':>5} {'solves':>20} {'Nsum':>6} {'ΔN vs 新鲜':>11}")
        fresh = None
        for d in run:
            if 100 <= d["t"] <= 100 + K + 2:
                if d["reused"] == 0:
                    fresh = d["Nsum"]
                dN = "" if fresh is None or d["reused"] == 0 else f"{d['Nsum']-fresh:+d}"
                print(f"    {d['t']:>4} {d['b']:>5} {d['t']-d['b']:>5} "
                      f"{str(d['solves']):>20} {d['Nsum']:>6} {dN:>11}")

    # ── 年龄曲线 ──
    print(f"\n{'='*100}")
    print("4. ★ 年龄曲线 N(a)：按 K 分别给出（不做跨 K 池化）")
    print(f"{'='*100}")
    for mode in ("sum", "first"):
        print(f"\n  ── {mode} 口径 ──")
        for K in (1, 2, 3, 5, 8):
            if K not in runs:
                continue
            bya = defaultdict(list)
            for d in runs[K]:
                bya[d["t"] - d["b"]].append(d["Nfirst"] if mode == "first" else d["Nsum"])
            line = "  ".join(f"a={a}:{st.mean(v):.1f}" for a, v in sorted(bya.items())[:12])
            print(f"  K={K}: {line}")

    # ── 确定性检验 ──
    print(f"\n{'='*100}")
    print("5. ★ 状态确定性检验：同样的 (t, a) 在不同 K 中是否给出同样的 N？")
    print(f"{'='*100}")
    for mode in ("sum", "first"):
        cells = defaultdict(set)
        for K, run in runs.items():
            for d in run:
                cells[(d["t"], d["t"] - d["b"])].add(
                    d["Nfirst"] if mode == "first" else d["Nsum"])
        multi = {k: v for k, v in cells.items() if len(v) > 1}
        print(f"\n  {mode} 口径：共 {len(cells)} 个 (t,a) 格子，"
              f"其中 N 取值不唯一的 {len(multi)} 个")
        if multi:
            worst = sorted(multi.items(), key=lambda kv: -(max(kv[1]) - min(kv[1])))[:8]
            for k, v in worst:
                vs = sorted(v)
                print(f"    (t={k[0]}, a={k[1]}): N ∈ {vs[:6]}{'...' if len(vs)>6 else ''} "
                      f"极差 {max(vs)-min(vs)}")

    # ── 关键判据的定量形式 ──
    print(f"\n{'='*100}")
    print("6. ★ 决策空间判据的定量形式")
    print(f"{'='*100}")
    if 1 in runs:
        base = runs[1]
        rmed = st.median([d["r"] for d in base if d["reused"] == 0])
        nsum_med = st.median([d["Nsum"] for d in base])
        nfirst_med = st.median([d["Nfirst"] for d in base])
        print(f"  实测：重建成本 r = {rmed:.2f}（一次 CG 迭代为单位）")
        print(f"        每步总迭代数（sum 口径）中位 = {nsum_med:.0f}")
        print(f"        每步首解迭代数（first 口径）中位 = {nfirst_med:.0f}")
        print(f"\n  每步重建代价占该步迭代代价的比例：")
        print(f"    sum   口径：r/{nsum_med:.0f} = {rmed/nsum_med*100:.1f}%")
        print(f"    first 口径：r/{nfirst_med:.0f} = {rmed/nfirst_med*100:.1f}%")
        print(f"\n  ⇒ 决策空间存在要求【每步劣化 ΔN_step < r = {rmed:.1f}】。")
        # 实测 ΔN
        for K in (2, 3, 5, 8):
            if K not in runs:
                continue
            seq = [d for d in runs[K] if d["t"] >= 100]
            dns = []
            for i in range(len(seq) - 1):
                if seq[i + 1]["reused"] == 1 and seq[i]["t"] + 1 == seq[i + 1]["t"]:
                    dns.append(seq[i + 1]["Nsum"] - seq[i]["Nsum"])
            if dns:
                print(f"    K={K}: 单步劣化 ΔN_sum 中位 = {st.median(dns):.0f}, "
                      f"均值 {st.mean(dns):.1f}, 范围 [{min(dns)}, {max(dns)}]")

    # ── 墙钟对照 ──
    print(f"\n{'='*100}")
    print("7. 墙钟对照（scan.log，仅作交叉验证）")
    print(f"{'='*100}")
    import glob
    if os.path.exists("scan.log"):
        wt = defaultdict(list)
        for ln in open("scan.log"):
            m = re.search(r"K=(\d+) rep=(\d+) et=([0-9.]+)s", ln)
            if m:
                wt[int(m.group(1))].append(float(m.group(3)))
        print(f"  {'K':>3} {'墙钟中位/s':>10} {'相对K=1':>10}  {'cost(sum)相对':>14}")
        for K in sorted(wt):
            med = st.median(wt[K])
            rel = f"{(med/st.median(wt[1])-1)*100:+9.2f}%" if 1 in wt else ""
            crel = f"{(cs[K]/cs[1]-1)*100:+13.2f}%" if K in cs else ""
            print(f"  {K:>3} {med:>10.2f} {rel:>10}  {crel:>14}")


if __name__ == "__main__":
    main()
