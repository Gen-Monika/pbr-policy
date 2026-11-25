#!/usr/bin/env python3
"""
★★ 核心实验：贪心规则能否复现离线最优周期？

═══════════════════════════════════════════════════════════════════════
动机（此前完全没试过的规则）
═══════════════════════════════════════════════════════════════════════
先前我只试过"平均代价"阈值规则（pred >= running_average），效果一般。

但注意一个被我忽略的量化事实（levels=5）：
    r = 35.0，而 N_step(0) = 42.0        ⇒ 两者【同量级】
⇒ 判据 ΔN(a) > r 会在【很小】的年龄上触发。
⇒ 一个极简单的【一步贪心】规则可能直接复现离线最优周期：

    ★ 重建 ⟺ 预测的 ΔN(a) > r
      其中 ΔN(a) = N_step(a) − N_step(0)

直觉验算：
    levels=5: ΔN(1) = 17 < 35 ⇒ 复用；ΔN(2) = 38 > 35 ⇒ 重建
              ⇒ 周期 2 ⇒ 与离线最优 K*=2 一致 ✓
    levels=2: ΔN(1) = 24 > 22.4 ⇒ 重建
              ⇒ 周期 1 ⇒ 与离线最优 K*=1 一致 ✓

═══════════════════════════════════════════════════════════════════════
要区分的三个层次
═══════════════════════════════════════════════════════════════════════
  G0  贪心 + 【真】年龄曲线          —— 该类策略的ceiling（用 oracle 信息但规则简单）
  G1  贪心 + 【在线学习】的年龄曲线  —— 真正可可实现的策略
  G2  贪心 + 【在线学习 + 局部窗口】 —— 应对非平稳（漂移随时间变快）

若 G1/G2 能接近 G0，则本方法的核心主张（"不依赖过强老化假设、
漂移未知仍能低成本做出接近最优的决策"）就得到直接支持。
"""
import os
import re
import json
import statistics as st
from collections import defaultdict, deque

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
REUSE_RE = re.compile(r"REUSE@(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")
T_MAX = 344

# levels=5 的实测 r（本次实验的目标配置）
R_L5 = 35.00
# levels=2 的实测 r（对照组）
R_L2 = 22.43

L5_LOG = "l5/log.k{}r{}"
L5_CSV = "l5_k{}_r{}.csv"
S_LOG = "s{}/log.s{}"
S_CSV = "s_k{}_r{}.csv"


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


def build_table(level):
    """建 (t,a) -> N_step 表，以及全局年龄曲线。"""
    cells = defaultdict(list)
    if level == 5:
        pairs = [(L5_LOG.format(K, R), L5_CSV.format(K, R))
                 for K in (1, 2, 3, 4, 5, 6, 8) for R in (1, 2, 3)]
        pairs += [(f"l5/log.big{R}", f"l5_big_r{R}.csv") for R in (1, 2)]
    else:
        pairs = [(S_LOG.format(K, R), S_CSV.format(K, R))
                 for K in (1, 2, 3, 4, 5, 6, 8) for R in (1, 2, 3)]
        pairs += [(f"sbig/log.big{R}", f"sbig_r{R}.csv") for R in (1, 2, 3)]
    for logp, csvp in pairs:
        if not (os.path.exists(logp) and os.path.exists(csvp)):
            continue
        steps, rows = parse_log(logp), load_csv(csvp)
        for i in range(min(len(steps), len(rows))):
            if rows[i]["tIter"] <= 0:
                continue
            t = i + 1
            b = steps[i]["b"] or t
            cells[(t, t - b)].append(sum(steps[i]["solves"]))
    return {k: st.median(v) for k, v in cells.items()}


def make_Nfn(tab):
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
    return Nfn, curve


# ─────────────────────────────────────────────────────────────────────
# 策略实现
# ─────────────────────────────────────────────────────────────────────
def sim_fixed(Nfn, r0, K, b0=100):
    tot, a = 0.0, 0
    for t in range(1, T_MAX + 1):
        if (t < b0) or ((t - b0) % K == 0):
            tot += r0 + Nfn(t, 0)
            a = 1
        else:
            tot += Nfn(t, a)
            a += 1
    return tot


def sim_greedy_true_curve(Nfn, curve, r0, b0=100, amax=80):
    """G0：用【真实】年龄曲线做贪心。重建 ⟺ ΔN(a) > r。"""
    n0 = curve[0]
    tot, a = 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            continue
        if a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            dn = curve.get(a, curve[max(curve)]) - n0
            rebuild = dn > r0
        if rebuild:
            tot += r0 + Nfn(t, 0)
            a = 1
        else:
            tot += Nfn(t, a)
            a += 1
    return tot


def sim_greedy_learned(Nfn, r0, b0=100, amax=40, window=None, prior_slope=1.0):
    """G1/G2：年龄曲线【在线学习】。

    - 只观测自己经历过的 (age, ΔN)
    - 用已观测年龄的最大值外推（保守）或线性外推
    - window 非 None 时只用最近 window 个样本（应对非平稳）
    """
    obs = deque(maxlen=window) if window else []
    tot, a = 0.0, 0
    n0_est = None
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            if n0_est is None:
                n0_est = Nfn(t, 0)
            continue
        # 决策
        if a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            # 用已观测的 (age, ΔN) 估计 ΔN(a)
            if obs:
                known = sorted(obs)
                ages = [x[0] for x in known]
                dns = [x[1] for x in known]
                if a in ages:
                    est = dns[ages.index(a)]
                else:
                    # 线性外推：用最后两个不同年龄的点
                    if len(known) >= 2 and ages[-1] > ages[-2]:
                        sl = (dns[-1] - dns[-2]) / (ages[-1] - ages[-2])
                        est = dns[-1] + sl * (a - ages[-1])
                    else:
                        est = dns[-1] + prior_slope * (a - ages[-1])
                est = max(0.0, est)
            else:
                est = prior_slope * a
            rebuild = est > r0
        if rebuild:
            n_now = Nfn(t, 0)
            tot += r0 + n_now
            a = 1
            if n0_est is None:
                n0_est = n_now
        else:
            n_now = Nfn(t, a)
            tot += n_now
            # 学到一条 (age=a, ΔN=N(a) − 最近一次重建时的 N(0))
            if n0_est is not None:
                obs.append((a, n_now - n0_est))
            a += 1
    return tot


def sim_avgcost(Nfn, r0, b0=100, predict=None, amax=80):
    """先前的平均代价阈值规则（作对照）。"""
    tot, a, hist = 0.0, 0, []
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            hist.append(Nfn(t, 0))
            continue
        avg = tot / (t - 1)
        pred = hist[-1] if predict is None else predict(hist, a)
        if a == 0 or a >= amax or pred >= avg:
            tot += r0 + Nfn(t, 0)
            a = 1
            hist.append(Nfn(t, 0))
        else:
            tot += Nfn(t, a)
            a += 1
            hist.append(Nfn(t, a))
    return tot


def sim_dp(Nfn, r0, AMAX=80):
    INF = float("inf")
    V = [[INF] * (AMAX + 1) for _ in range(T_MAX + 1)]
    A_ = [[1] * (AMAX + 1) for _ in range(T_MAX + 1)]
    for a in range(AMAX + 1):
        V[T_MAX][a] = 0.0
    for t in range(T_MAX - 1, -1, -1):
        for a in range(AMAX + 1):
            cr = r0 + Nfn(t, 0) + V[t + 1][0]
            ck = Nfn(t, a) + V[t + 1][a + 1] if a < AMAX else INF
            if cr <= ck:
                V[t][a], A_[t][a] = cr, 1
            else:
                V[t][a], A_[t][a] = ck, 0
    tot, a, nr, path = 0.0, 0, 0, []
    for t in range(T_MAX):
        if A_[t][a] == 1:
            tot += r0 + Nfn(t + 1, 0)
            nr += 1
            a = 0
            path.append(t + 1)
        else:
            tot += Nfn(t + 1, a)
            a += 1
    return tot, nr, path


def report(level, r0):
    print(f"\n{'#'*100}")
    print(f"#  levels = {level}，r = {r0}")
    print(f"{'#'*100}")
    tab = build_table(level)
    if not tab:
        print("  （无数据）")
        return None
    Nfn, curve = make_Nfn(tab)
    print(f"  表：{len(tab)} 格，年龄覆盖 a ∈ [0, {max(a for _, a in tab)}]")
    print(f"  年龄曲线 N_step(a)（a=0..10）: "
          + " ".join(f"{curve.get(a, float('nan')):.0f}" for a in range(11)))

    base = sim_fixed(Nfn, r0, 1)
    orc, orcnr, orcpath = sim_dp(Nfn, r0)
    print(f"\n  {'策略':>34} {'代价':>10} {'相对K=1':>9} {'Regret':>9}")
    res = {}

    # 离线最优固定周期
    fixed = {K: sim_fixed(Nfn, r0, K) for K in range(1, 13)}
    bestK = min(fixed, key=fixed.get)
    print(f"  {'K=1 每步重建':>34} {base:>10.1f} {0.0:>8.2f}% "
          f"{(base/orc-1)*100:>8.2f}%")
    print(f"  {f'K*={bestK} 离线最优固定周期':>34} {fixed[bestK]:>10.1f} "
          f"{(fixed[bestK]/base-1)*100:>8.2f}% {(fixed[bestK]/orc-1)*100:>8.2f}%")

    # G0
    g0 = sim_greedy_true_curve(Nfn, curve, r0)
    res["G0_greedy_tru e"] = g0
    print(f"  {'G0 贪心 + 真年龄曲线':>34} {g0:>10.1f} "
          f"{(g0/base-1)*100:>8.2f}% {(g0/orc-1)*100:>8.2f}%")

    # G1 / G2
    for name, kw in [("G1 贪心 + 在线学习(全局)", dict(window=None)),
                     ("G2 贪心 + 在线学习(窗64)", dict(window=64)),
                     ("G3 贪心 + 在线学习(窗24)", dict(window=24)),
                     ("G4 贪心 + 在线学习(窗8)", dict(window=8))]:
        c = sim_greedy_learned(Nfn, r0, **kw)
        res[name] = c
        print(f"  {name:>34} {c:>10.1f} "
              f"{(c/base-1)*100:>8.2f}% {(c/orc-1)*100:>8.2f}%")

    # 平均代价规则（旧）
    for name, pf in [("P4a 平均代价+上一值", None)]:
        c = sim_avgcost(Nfn, r0)
        res[name] = c
        print(f"  {name:>34} {c:>10.1f} "
              f"{(c/base-1)*100:>8.2f}% {(c/orc-1)*100:>8.2f}%")

    print(f"  {'真 oracle（不可实现）':>34} {orc:>10.1f} "
          f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")
    print(f"\n  oracle 重建 {orcnr} 次，间隔中位 "
          f"{st.median([y-x for x,y in zip(orcpath, orcpath[1:])]):.0f}")

    # G0 的实际重建周期
    a_chk = 0
    intervals = []
    last = None
    tot2, a2 = 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < 100:
            rb = True
        elif a2 == 0:
            rb = True
        elif a2 >= 80:
            rb = True
        else:
            rb = (curve.get(a2, curve[max(curve)]) - curve[0]) > r0
        if rb:
            if last is not None:
                intervals.append(t - last)
            last = t
            a2 = 1
        else:
            a2 += 1
    post = [x for x in intervals if x > 0]
    if post:
        print(f"  G0 的重建间隔分布：中位 {st.median(post):.0f}，"
              f"范围 [{min(post)}, {max(post)}]")
    return dict(level=level, r=r0, base=base, bestK=bestK, fixed=fixed[bestK],
                oracle=orc, oracle_nreb=orcnr, policies=res)


def main():
    print("=" * 100)
    print("★★ 贪心规则（ΔN(a) > r）能否复现离线最优周期？")
    print("=" * 100)
    out = []
    for level, r0 in ((5, R_L5), (2, R_L2)):
        d = report(level, r0)
        if d:
            out.append(d)

    # ── 总结 ──
    print(f"\n{'='*100}")
    print("★ 总结：各策略的 regret（相对真 oracle）")
    print(f"{'='*100}")
    for d in out:
        print(f"\n  levels={d['level']}（r={d['r']:.1f}，离线最优 K*={d['bestK']}）")
        print(f"    K=1 每步重建              : {(d['base']/d['oracle']-1)*100:6.2f}%")
        print(f"    K*={d['bestK']} 离线最优固定周期   : "
              f"{(d['fixed']/d['oracle']-1)*100:6.2f}%")
        for k, v in d["policies"].items():
            print(f"    {k:26s}: {(v/d['oracle']-1)*100:6.2f}%")
        print(f"    真 oracle                 :   0.00%")

    with open("greedy_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n⇒ 写入 greedy_result.json")


if __name__ == "__main__":
    main()
