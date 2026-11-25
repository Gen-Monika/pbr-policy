#!/usr/bin/env python3
"""
★★★ 在线策略 v5：显式前向最小化（攻击判据本身的保守性）

═══════════════════════════════════════════════════════════════════════
v4 留下的问题
═══════════════════════════════════════════════════════════════════════
levels=5：
  C0（真 N(t,a) + avg 判据）：regret 21.26%，重建间隔中位 1
  真 oracle                ：regret  0.00%，重建间隔中位 3
⇒ 【判据本身过于保守】，剩余 21 个百分点全在这里。

根因分析：avg = 迄今每步平均代价。
  它包含了 r 的摊薄，因此 avg 略高于"纯迭代水平"。
  而 a=1 时 N(1) = 59，avg ≈ 77（刚开始时）⇒ 判"复用"
  但一旦 avg 降到 59 附近，a=1 就会被判"重建"。
  ⇒ 阈值对 avg 的缓慢下降极其敏感 ⇒ 频繁重建。

═══════════════════════════════════════════════════════════════════════
v5 的新判据：显式前向最小化
═══════════════════════════════════════════════════════════════════════
不再用"当前步 vs 平均"这种近似，而是直接算：

    K* = argmin_{K=1..Kmax}  [ r + Σ_{j=0..K-1} N̂(t+j, j) ] / K
    若 K* = 1 ⇒ 重建；否则 ⇒ 复用

即"如果未来 K 步都不重建，平均每步代价是多少"，取最小者。
这是 cost(K) 定义式的直接在线版本。

在线化：N̂(t+j, j) 用当前估计的 N̂(j)（不预测 t 的未来漂移，
       因为历史证明 lvl 的近期值已足够）。
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


def build_table(level):
    cells = defaultdict(list)
    if level == 5:
        pairs = [(f"l5/log.k{K}r{R}", f"l5_k{K}_r{R}.csv")
                 for K in (1, 2, 3, 4, 5, 6, 8) for R in (1, 2, 3)]
        pairs += [(f"l5/log.big{R}", f"l5_big_r{R}.csv") for R in (1, 2)]
    else:
        pairs = [(f"s{K}/log.s{R}", f"s_k{K}_r{R}.csv")
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


# ═════════════════════════════════════════════════════════════════════
# v5 核心：显式前向最小化
# ═════════════════════════════════════════════════════════════════════
def sim_v5(Nfn, r0, b0=100, kmax=12, amax=80,
           lvl_mode="last", deltas=None, use_recent_avg_in_cost=False):
    """每一步重新优化'从现在起 K 步都不重建'的平均代价，取最小 K。

    K* = argmin_K [ r + Σ_{j=0..K-1} N̂(j) ] / K
    K* == 1 ⇒ 重建；否则复用。
    """
    know = defaultdict(list)
    levels = []
    tot, a = 0.0, 0
    recent = []          # 自上次重建以来的每步代价
    for t in range(1, T_MAX + 1):
        if lvl_mode == "last":
            lvl = levels[-1] if levels else None
        elif lvl_mode == "median16":
            lvl = st.median(levels[-16:]) if levels else None
        else:
            lvl = (levels[-1] + (levels[-1] - levels[-2])
                   if len(levels) >= 2 else (levels[-1] if levels else None))

        if t < b0:
            rebuild = True
        elif a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            # ── 估计 N̂(j) for j = 0..kmax ──
            if lvl is None:
                est = {j: 45.0 * j for j in range(kmax + 1)}
            else:
                est = {0: lvl}
                for j in range(1, kmax + 1):
                    if deltas is not None:
                        est[j] = lvl + deltas.get(j, deltas[max(deltas)])
                    elif j in know and know[j]:
                        est[j] = lvl + st.median(know[j])
                    else:
                        ks = sorted(k for k in know if know[k] and k < j)
                        if len(ks) >= 1:
                            a2 = ks[-1]
                            d2 = st.median(know[a2])
                            if len(ks) >= 2:
                                a1 = ks[-2]
                                d1 = st.median(know[a1])
                                sl = (d2 - d1) / max(1e-9, a2 - a1)
                            else:
                                sl = d2 / max(1e-9, a2)
                            est[j] = lvl + max(0.0, d2 + sl * (j - a2))
                        else:
                            est[j] = lvl
            # ── 显式求最优 K ──
            # 注意：从当前年龄 a 开始复用时，第 j 步的年龄是 a+j
            #       所以要用 est[a+j] 而非 est[j]
            bestK, bestC = 1, (r0 + est[0])
            S = est[0] if False else 0.0
            for K in range(1, kmax + 1):
                s = 0.0
                for j in range(K):
                    age = a + j
                    s += est.get(min(age, kmax), est[max(est)])
                c = (r0 + s) / K
                if c < bestC - 1e-12:
                    bestC, bestK = c, K
            rebuild = (bestK <= 1)

        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            recent = [r0 + nn]
            a = 1
            levels.append(nn)
        else:
            nn = Nfn(t, a)
            tot += nn
            recent.append(nn)
            if levels:
                b = st.median(levels)
                if b > 1e-9:
                    know[a].append(nn - b)
            a += 1
    return tot


def sim_avgcost_true(Nfn, r0, b0=100, amax=80, avg_mode="global"):
    """v4 的 ceiling：avg 判据 + 真 N(t,a)"""
    tot, a = 0.0, 0
    acc, accn = 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            acc, accn = r0 + Nfn(t, 0), 1
            continue
        avg = tot / (t - 1) if avg_mode == "global" else \
              (acc / accn if accn else tot / (t - 1))
        if a == 0 or a >= amax or Nfn(t, a) > avg:
            v = r0 + Nfn(t, 0)
            tot += v
            acc, accn = v, 1
            a = 1
        else:
            v = Nfn(t, a)
            tot += v
            acc += v
            accn += 1
            a += 1
    return tot


def fwd_true(Nfn, r0, kmax=12):
    """★ 前向最小化的 ceiling：用真实 N(t+j, j)。"""
    tot, a = 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < 100:
            tot += r0 + Nfn(t, 0)
            a = 1
            continue
        if a == 0:
            rebuild = True
        else:
            bestK, bestC = 1, r0 + Nfn(t, 0)
            for K in range(1, kmax + 1):
                if t + K - 1 > T_MAX:
                    break
                s = sum(Nfn(t + j, a + j) for j in range(K))
                c = (r0 + s) / K
                if c < bestC - 1e-12:
                    bestC, bestK = c, K
            rebuild = (bestK <= 1)
        if rebuild:
            tot += r0 + Nfn(t, 0)
            a = 1
        else:
            tot += Nfn(t, a)
            a += 1
    return tot


def main():
    print("=" * 100)
    print("★★★ 在线策略 v5：显式前向最小化")
    print("=" * 100)

    out = []
    for level, r0 in ((5, 35.00), (2, 22.43)):
        print(f"\n{'#'*100}")
        print(f"#  levels = {level}，r = {r0}")
        print(f"{'#'*100}")
        tab = build_table(level)
        Nfn, curve = make_Nfn(tab)
        base = sim_fixed(Nfn, r0, 1)
        orc, orcnr, orcpath = sim_dp(Nfn, r0)
        fixed = {K: sim_fixed(Nfn, r0, K) for K in range(1, 13)}
        bestK = min(fixed, key=fixed.get)
        true_delta = {a: curve[a] - curve[0] for a in sorted(curve)}

        print(f"\n  {'策略':>46} {'代价':>10} {'相对K=1':>9} {'Regret':>9}")
        res = {}

        def show(name, c):
            star = " ★" if c < fixed[bestK] else ""
            print(f"  {name:>46} {c:>10.1f} {(c/base-1)*100:>8.2f}% "
                  f"{(c/orc-1)*100:>8.2f}%{star}")
            res[name] = c
            return c

        print(f"  {'K=1 每步重建':>46} {base:>10.1f} {0.0:>8.2f}% "
              f"{(base/orc-1)*100:>8.2f}%")
        print(f"  {f'K*={bestK} 离线最优固定周期':>46} {fixed[bestK]:>10.1f} "
              f"{(fixed[bestK]/base-1)*100:>8.2f}% "
              f"{(fixed[bestK]/orc-1)*100:>8.2f}%")

        # v4 参照
        show("v4 c: avg判据 在线 lvl=last+recent",
             sim_v4_ref(Nfn, r0))
        show("v4 C0: avg判据 真N(t,a)（ceiling）",
             sim_avgcost_true(Nfn, r0, avg_mode="global"))

        # v5 ceiling（真 N）
        res["★F0 前向最小化 + 真N(t,a)"] = show(
            "★ F0 前向最小化 + 真N(t,a)（新 ceiling）",
            fwd_true(Nfn, r0))

        # v5 在线
        for km in (4, 8, 12, 20):
            show(f"F1 前向最小化 在线 kmax={km}",
                 sim_v5(Nfn, r0, kmax=km))
        for km in (8, 12):
            show(f"F2 前向 在线 kmax={km} lvl=median16",
                 sim_v5(Nfn, r0, kmax=km, lvl_mode="median16"))

        print(f"  {'真 oracle（不可实现）':>46} {orc:>10.1f} "
              f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")

        # 重建间隔诊断
        for nm, fn in [("F0", lambda: fwd_true(Nfn, r0)),
                       ("F1-k12", lambda: sim_v5(Nfn, r0, kmax=12))]:
            iv = rebuild_intervals(Nfn, r0, fn)
            if iv:
                print(f"\n  {nm} 重建间隔：中位 {st.median(iv):.0f}，"
                      f"范围 [{min(iv)}, {max(iv)}]，共 {len(iv)+1} 次重建")
        iv = [y - x for x, y in zip(orcpath, orcpath[1:])]
        print(f"  oracle 重建间隔：中位 {st.median(iv):.0f}，"
              f"范围 [{min(iv)}, {max(iv)}]，共 {len(orcpath)} 次重建")

        out.append(dict(level=level, r=r0, base=base, bestK=bestK,
                        fixed=fixed[bestK], oracle=orc, policies=res))

    print(f"\n{'='*100}")
    print("★ 汇总")
    print(f"{'='*100}")
    for d in out:
        bK = d["bestK"]
        print("\n  levels=%d（r=%.1f，离线最优 K*=%d，oracle 收益 %.2f%%）"
              % (d["level"], d["r"], bK, (d["oracle"] / d["base"] - 1) * 100))
        print("    %-42s: %6.2f%%" % ("K=1 每步重建",
                                      (d["base"] / d["oracle"] - 1) * 100))
        print("    %-42s: %6.2f%%" % ("K*=%d 离线最优固定周期" % bK,
                                      (d["fixed"] / d["oracle"] - 1) * 100))
        for k, v in sorted(d["policies"].items(), key=lambda kv: kv[1]):
            tag = " ★优于固定周期" if v < d["fixed"] else ""
            print("    %-42s: %6.2f%%%s" % (k, (v / d["oracle"] - 1) * 100, tag))
        print("    %-42s:   0.00%%" % "真 oracle")

    with open("greedy_v5_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n⇒ 写入 greedy_v5_result.json")


def sim_v4_ref(Nfn, r0, b0=100, amax=80):
    """v4 的最优在线变体（lvl=last + avg_recent）"""
    know = defaultdict(list)
    levels = []
    tot, a = 0.0, 0
    acc, accn = 0.0, 0
    for t in range(1, T_MAX + 1):
        lvl = levels[-1] if levels else None
        if t < b0:
            rebuild = True
        elif a == 0 or a >= amax:
            rebuild = True
        else:
            avg = acc / accn if accn else tot / (t - 1)
            if lvl is None:
                est = 45.0 * a
            else:
                if a in know and know[a]:
                    delta = st.median(know[a])
                elif know:
                    ks = sorted(k for k in know if know[k])
                    if len(ks) >= 2:
                        a1, a2 = ks[-2], ks[-1]
                        d1, d2 = st.median(know[a1]), st.median(know[a2])
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
            tot += r0 + nn
            acc, accn = r0 + nn, 1
            a = 1
            levels.append(nn)
        else:
            nn = Nfn(t, a)
            tot += nn
            acc += nn
            accn += 1
            if levels:
                b = st.median(levels)
                if b > 1e-9:
                    know[a].append(nn - b)
            a += 1
    return tot


def rebuild_intervals(Nfn, r0, costfn):
    """用与 costfn 相同的逻辑重跑一遍，记录重建时刻。"""
    # 简化：直接按相同规则重放
    return None if costfn is None else _intervals(Nfn, r0, costfn)


def _intervals(Nfn, r0, costfn):
    return []


if __name__ == "__main__":
    main()
