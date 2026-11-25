#!/usr/bin/env python3
"""
★★★ 在线策略 v4：三个估计器改进 + avg_recent

═══════════════════════════════════════════════════════════════════════
v3 确立的事实
═══════════════════════════════════════════════════════════════════════
判据形式正确：复用有益 ⟺ N(t,a) < avg
  C0（真 N(t,a)）：levels=5 → regret 22.17%（★优于离线最优 27.43%）
                   levels=2 → regret  9.25%（★优于离线最优 13.60%）
  C1（在线学习）：levels=5 → 32.51%（劣于固定周期！）
⇒ 差距 100% 来自 N̂ 的估计误差。

═══════════════════════════════════════════════════════════════════════
v4 的四项改进
═══════════════════════════════════════════════════════════════════════
改进1【lvl 用近期值而非滞后中位】
    旧：lvl = median(最近 16 次重建的 N(0))
    新：lvl = 最近一次重建的 N(0)（并可选加趋势）
    理由：N(0) 自身随物理时间漂移，滞后中位会引入系统偏差。

改进2【δ̂ 用两步增量比预测爆炸】
    观测 δ(a) = N(a) − N(0)。
    线性段 δ(a)/δ(a−1) ≈ 1.3；接近爆炸时该比值陡增。
    当比值超过阈值时，即使 N̂(a) 未超 avg 也重建。

改进3【avg 改用"自上�次重建以来"的局部均值】
    旧：avg = 全程累计 / 已走步数
    新：avg_recent = (自上次重建以来的累计代价) / (自上次重建以来的步数)
    理由：消除前期密集重建对 avg 的污染（v3 的 C0 比 oracle 保守：
          间隔中位 1 vs 3）。

改进4【显式"未来 K 步"判据（可选）】
    不用 avg，而直接最小化 (r + Σ_{j≤K} N̂(j))/K。
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
# v4 核心：可配置的在线策略
# ═════════════════════════════════════════════════════════════════════
def sim_v4(Nfn, r0, b0=100, amax=80,
           lvl_mode="last",        # last | median16 | trend
           avg_mode="recent",      # global | recent
           ratio_thresh=None,      # 如 2.0：两步增量比超阈值即重建
           deltas=None):
    """deltas=None 表示在线学习；传入真实 δ(a) 字典则为 ceiling 模式。"""
    know = defaultdict(list)
    levels = []
    tot, a = 0.0, 0
    acc, acc_steps = 0.0, 0        # 自上次重建以来的累计
    for t in range(1, T_MAX + 1):
        # ── lvl 估计 ──
        if lvl_mode == "last":
            lvl = levels[-1] if levels else None
        elif lvl_mode == "median16":
            lvl = st.median(levels[-16:]) if levels else None
        else:  # trend：用最近两次的差外推
            if len(levels) >= 2:
                lvl = levels[-1] + (levels[-1] - levels[-2])
            elif levels:
                lvl = levels[-1]
            else:
                lvl = None

        if t < b0:
            rebuild = True
        elif a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            avg = (tot / (t - 1)) if avg_mode == "global" else \
                  ((acc / acc_steps) if acc_steps > 0 else (tot / (t - 1)))
            # ── δ(a) 估计 ──
            if deltas is not None:
                delta = deltas.get(a, deltas[max(deltas)])
            elif a in know and know[a]:
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
            est = (lvl + max(0.0, delta)) if lvl is not None else (45.0 * a)
            rebuild = est > avg

            # ── 改进2：两步增量比 ──
            if not rebuild and ratio_thresh is not None and know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a1, a2 = ks[-2], ks[-1]
                    d1, d2 = st.median(know[a1]), st.median(know[a2])
                    if d1 > 1e-9 and d2 / d1 >= ratio_thresh:
                        rebuild = True

        # ── 执行 ──
        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            acc, acc_steps = r0 + nn, 1
            a = 1
            levels.append(nn)
        else:
            nn = Nfn(t, a)
            tot += nn
            acc += nn
            acc_steps += 1
            if levels:
                b = st.median(levels)
                if b > 1e-9:
                    know[a].append(nn - b)
            a += 1
    return tot


def main():
    print("=" * 100)
    print("★★★ 在线策略 v4：估计器改进")
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

        # 真实 δ(a)（供 ceiling）
        true_delta = {a: curve[a] - curve[0] for a in sorted(curve)}

        print(f"  曲线 N(0..10): " + " ".join(f"{curve.get(a,0):.0f}"
                                                for a in range(11)))
        print(f"\n  {'策略':>44} {'代价':>10} {'相对K=1':>9} {'Regret':>9}")

        def show(name, c):
            star = " ★" if c < fixed[bestK] else ""
            print(f"  {name:>44} {c:>10.1f} {(c/base-1)*100:>8.2f}% "
                  f"{(c/orc-1)*100:>8.2f}%{star}")
            return c

        res = {}
        print(f"  {'K=1 每步重建':>44} {base:>10.1f} {0.0:>8.2f}% "
              f"{(base/orc-1)*100:>8.2f}%")
        print(f"  {f'K*={bestK} 离线最优固定周期':>44} {fixed[bestK]:>10.1f} "
              f"{(fixed[bestK]/base-1)*100:>8.2f}% "
              f"{(fixed[bestK]/orc-1)*100:>8.2f}%")

        # ceiling 对照
        res["C0 真N(t,a) avg_global"] = show(
            "C0 真N(t,a)+avg全程（v3 ceiling）",
            sim_v4(Nfn, r0, lvl_mode="median16", avg_mode="global",
                   deltas=true_delta))
        res["C0r 真N(t,a) avg_recent"] = show(
            "★ C0r 真N(t,a)+avg_recent",
            sim_v4(Nfn, r0, lvl_mode="median16", avg_mode="recent",
                   deltas=true_delta))

        # 在线：逐项加改进
        res["a"] = show("a 在线 lvl=median16 avg=global（v3）",
                        sim_v4(Nfn, r0, lvl_mode="median16", avg_mode="global"))
        res["b"] = show("b 在线 lvl=last avg=global",
                        sim_v4(Nfn, r0, lvl_mode="last", avg_mode="global"))
        res["c"] = show("★ c 在线 lvl=last avg=recent",
                        sim_v4(Nfn, r0, lvl_mode="last", avg_mode="recent"))
        res["d"] = show("d 在线 lvl=trend avg=recent",
                        sim_v4(Nfn, r0, lvl_mode="trend", avg_mode="recent"))
        for rt in (1.5, 2.0, 3.0):
            res[f"e{rt}"] = show(
                f"e 在线 lvl=last avg=recent +ratio>{rt}",
                sim_v4(Nfn, r0, lvl_mode="last", avg_mode="recent",
                       ratio_thresh=rt))
        res["f"] = show("f 在线 lvl=trend avg=recent +ratio>1.5",
                        sim_v4(Nfn, r0, lvl_mode="trend", avg_mode="recent",
                               ratio_thresh=1.5))

        print(f"  {'真 oracle（不可实现）':>44} {orc:>10.1f} "
              f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")
        out.append(dict(level=level, r=r0, base=base, bestK=bestK,
                        fixed=fixed[bestK], oracle=orc, policies=res))

    print(f"\n{'='*100}")
    print("★ 汇总：regret（相对真 oracle）")
    print(f"{'='*100}")
    for d in out:
        bK = d["bestK"]
        print("\n  levels=%d（r=%.1f，离线最优 K*=%d，oracle 收益 %.2f%%）"
              % (d["level"], d["r"], bK, (d["oracle"] / d["base"] - 1) * 100))
        print("    %-40s: %6.2f%%" % ("K=1 每步重建",
                                      (d["base"] / d["oracle"] - 1) * 100))
        print("    %-40s: %6.2f%%" % ("K*=%d 离线最优固定周期" % bK,
                                      (d["fixed"] / d["oracle"] - 1) * 100))
        for k, v in sorted(d["policies"].items(), key=lambda kv: kv[1]):
            tag = " ★优于固定周期" if v < d["fixed"] else ""
            print("    %-40s: %6.2f%%%s" % (k, (v / d["oracle"] - 1) * 100, tag))
        print("    %-40s:   0.00%%" % "真 oracle")

    with open("greedy_v4_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n⇒ 写入 greedy_v4_result.json")


if __name__ == "__main__":
    main()
