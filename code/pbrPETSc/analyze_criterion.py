#!/usr/bin/env python3
"""
★ 结构性判据：每次构造服务多少次求解，直接决定决策空间的宽窄。

═══════════════════════════════════════════════════════════════════════
推导
═══════════════════════════════════════════════════════════════════════
设一个时间步内有 s 次压力求解，但只有 1 次预条件子构造（实测 s=3）。

  重建该步代价 = r + Σ_{i=1..s} N_i(0)          （r = t_pcsetup/t_iter）
  复用一个年龄 a 的旧预条件子 = Σ_{i=1..s} N_i(a)

  复用胜出 ⟺ Σ N_i(a) < Σ N_i(0) + r
          ⟺ ΔN_step(a) < r        （ΔN_step = 该步 s 次求解的总劣化）

若劣化在各次求解间均匀，即 ΔN_step ≈ s · ΔN_single，则

  ★ 复用胜出 ⟺ ΔN_single < r / s

⇒ 【每步求解次数 s 直接缩小决策空间】。这是本项目新发现的结构性约束，
   在此前的分析中完全未被识别（因为旧代码把 s 次求解误当成 1 次）。

═══════════════════════════════════════════════════════════════════════
本脚本要回答
═══════════════════════════════════════════════════════════════════════
1. r/s 的实测值是多少？ΔN_single 是多少？判据是否成立？
2. ΔN 是否随时间变化？若前期小、后期大，则决策空间在【时间上非平稳】
   —— 这正是论文要的"跨轮非平稳"形态。
3. 提高 ILU 填充层级能否让 r 超过门限？
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
        out.append(dict(t=i + 1, b=s["b"] or (i + 1), reused=s["reused"],
                        solves=s["solves"], Nsum=sum(s["solves"]),
                        tsetup=r["tPCSetup"], titer=r["tIter"],
                        r=r["tPCSetup"] / r["tIter"]))
    return out


def main():
    S = 3   # 实测：每步 3 次压力求解

    print("=" * 100)
    print("★ 结构性判据：复用胜出 ⟺ ΔN_single < r / s")
    print("=" * 100)

    runs = {K: load_run(K) for K in (1, 2, 3, 4, 5, 6, 8)}
    runs = {k: v for k, v in runs.items() if v}

    r0 = st.median([d["r"] for d in runs[1] if d["reused"] == 0])
    print(f"\n  每步求解次数 s = {S}")
    print(f"  重建成本 r = {r0:.2f}（一次 CG 迭代为单位）")
    print(f"  ★ 门限 r/s = {r0/S:.2f}   ← ΔN_single 必须低于它才值得复用")

    # ── 1. 年龄曲线（sum 口径，按 K 分别） ──
    print(f"\n{'='*100}")
    print("1. 年龄曲线 N_step(a)（每步 s 次求解之和）")
    print(f"{'='*100}")
    print(f"  {'K':>3} " + "".join(f"{'a='+str(a):>9}" for a in range(8)))
    curves = {}
    for K in sorted(runs):
        bya = defaultdict(list)
        for d in runs[K]:
            bya[d["t"] - d["b"]].append(d["Nsum"])
        curves[K] = {a: st.mean(v) for a, v in bya.items()}
        print(f"  {K:>3} " + "".join(
            f"{curves[K][a]:>9.1f}" if a in curves[K] else f"{'-':>9}" for a in range(8)))

    print(f"\n  ⇒ 逐步劣化 ΔN_step(a) = N_step(a) − N_step(0)：")
    print(f"  {'a':>3} {'ΔN_step':>10} {'vs r':>10} {'判定':>12}")
    for a in range(1, 8):
        if a in curves[8]:
            dn = curves[8][a] - curves[8][0]
            print(f"  {a:>3} {dn:>10.1f} {dn-r0:>+10.1f} "
                  f"{'复用 ✓' if dn < r0 else '重建 ✗':>12}")

    # ── 2. ★ ΔN 随时间变化（决策空间的非平稳性） ──
    print(f"\n{'='*100}")
    print("2. ★ ΔN_step 随【时间区域】的变化（若前期小后期大，则决策空间非平稳）")
    print(f"{'='*100}")

    # 用 K=8 的思路：比较同一 t 的 a=0 与 a=1
    # 但 K=8 只在 t=100,108,116... 重建。改用跨 K 配对：
    # 对每个 t，找 (t, a=0) 和 (t, a=1) 的观测
    a0, a1 = {}, {}
    for K, run in runs.items():
        for d in run:
            a = d["t"] - d["b"]
            if a == 0:
                a0[d["t"]] = d["Nsum"]
            elif a == 1:
                a1.setdefault(d["t"], []).append(d["Nsum"])

    common = sorted(set(a0) & set(a1))
    print(f"  同时有 (t,a=0) 与 (t,a=1) 观测的 t 共 {len(common)} 个")
    print(f"\n  {'步段':>12} {'ΔN_step(0→1) 中位':>20} {'样本':>6} {'vs r=%.1f' % r0:>10}")
    for lo, hi in ((1, 50), (51, 100), (101, 150), (151, 200), (201, 250),
                   (251, 300), (301, 344)):
        ds = [st.mean(a1[t]) - a0[t] for t in common if lo <= t <= hi]
        if ds:
            med = st.median(ds)
            print(f"  {f'{lo}-{hi}':>12} {med:>20.1f} {len(ds):>6} "
                  f"{'复用 ✓' if med < r0 else '重建 ✗':>10}")

    # ── 3. 门限所需的 r ──
    print(f"\n{'='*100}")
    print("3. ★ 要打开决策空间，r 需要多大？")
    print(f"{'='*100}")
    all_dn1 = [st.mean(a1[t]) - a0[t] for t in common]
    print(f"  实测 ΔN_step(0→1)：中位 {st.median(all_dn1):.1f}，"
          f"最小 {min(all_dn1):.1f}，最大 {max(all_dn1):.1f}")
    print(f"  当前 r = {r0:.2f}")
    print(f"  ⇒ 需要 r > {st.median(all_dn1):.1f}（按中位劣化）")
    print(f"  ⇒ 若按最小劣化 {min(all_dn1):.1f}，需要 r > {min(all_dn1):.1f}")

    # ── 4. ILU 填充层级能否达到 ──
    print(f"\n{'—'*100}")
    print("4. ILU 填充层级实测的 r（来自 bench_ilu_levels.csv）")
    print(f"{'—'*100}")
    if os.path.exists("bench_ilu_levels.csv"):
        by = defaultdict(list)
        for ln in open("bench_ilu_levels.csv"):
            p = ln.rstrip("\n").split(",")
            if len(p) < 19:
                continue
            try:
                lv = int(float(p[3]))
                rv = float(p[17])
            except ValueError:
                continue
            if rv > 0:
                by[lv].append(rv)
        print(f"  {'levels':>7} {'样本':>6} {'r 中位':>10} {'可达?':>10}")
        for lv in sorted(by):
            med = st.median(by[lv])
            need = st.median(all_dn1)
            print(f"  {lv:>7} {len(by[lv]):>6} {med:>10.2f} "
                  f"{'✓ 超过门限' if med > need else '✗ 不足':>10}")

    # ── 5. 墙钟对照 ──
    print(f"\n{'='*100}")
    print("5. 墙钟交叉验证（scan.log）")
    print(f"{'='*100}")
    if os.path.exists("scan.log"):
        wt = defaultdict(list)
        for ln in open("scan.log"):
            m = re.search(r"K=(\d+) rep=(\d+) et=([0-9.]+)s", ln)
            if m:
                wt[int(m.group(1))].append(float(m.group(3)))
        print(f"  {'K':>3} {'墙钟中位/s':>11} {'相对K=1':>10}")
        base = st.median(wt[1]) if 1 in wt else None
        for K in sorted(wt):
            med = st.median(wt[K])
            rel = f"{(med/base-1)*100:+9.2f}%" if base else ""
            print(f"  {K:>3} {med:>11.2f} {rel:>10}")
        print(f"\n  ⚠️ 注意：这是 scan.sh 的【成组运行】结果，不是交错测量。")
        print(f"     此前交错重测（interleaved_k1_vs_k3）给出 K=3 vs K=1 = −4.35%，")
        print(f"     与该表的 −34.51% 矛盾 ⇒ 该表不可用于结论。")


if __name__ == "__main__":
    main()
