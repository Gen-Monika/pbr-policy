#!/usr/bin/env python3
"""
★★ 在线贪心策略 v2：修补"信息缺口"

═══════════════════════════════════════════════════════════════════════
v1（greedy_policy.py）的诊断结论
═══════════════════════════════════════════════════════════════════════
  G0（用真年龄曲线）        : regret 21.26%   ← 优于离线最优固定周期 27.43%
  G1..G4（在线学习曲线）    : regret 27.2–38.8%  ← 未复现 G0

根因：G0 的重建间隔中位为 2 ⇒ 在线版本几乎观察不到 a ≥ 3 的样本
      ⇒ 学不到 a ≥ 8 的爆炸段 ⇒ 以为"年龄大些也无妨" ⇒ 过晚重建。

═══════════════════════════════════════════════════════════════════════
v2 的两个修法
═══════════════════════════════════════════════════════════════════════
修法 A【冷启动探针】：前 P 步故意强制复用，不看判据，
        以一次性测出 ΔN(1..P) 的曲线，然后再进入贪心模式。
        —— 代价是探针期可能付一些劣化，收益是后续决策有依据。

修法 B【加速检测】：a=1..7 段线性（每步约 +45 迭代），爆炸在 a=8。
        用观测到的相邻增量比判断"是否接近爆炸"：
            ratio(a) = ΔN(a) / ΔN(a-1)
        线性段 ratio ≈ 1.0–1.3；接近爆炸时 ratio 会陡增。
        当 ratio 超过阈值即重建，无需等到 ΔN(a) > r。

两者可组合（A + B）。
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


# ─────────────────────────────────────────────────────────────────────
# v2 策略
# ─────────────────────────────────────────────────────────────────────
def sim_probe_greedy(Nfn, r0, probe_len=3, probe_every=40, b0=100, amax=60,
                     ratio_thresh=None):
    """★ 冷启动探针 + 贪心。

    probe_len   : 每次探针期强制复用的步数
    probe_every : 每隔多少步做一次探针（0 = 只在开始时探一次）
    ratio_thresh: 若非 None，则用"增量比"作为额外重建条件
    """
    know = {}           # age -> ΔN 观测
    tot, a = 0.0, 0
    n0 = None
    since_probe = 0
    in_probe = 0
    for t in range(1, T_MAX + 1):
        force_rebuild = False
        # 是否该启动探针
        if t >= b0 and since_probe >= probe_every and in_probe == 0 and a == 0:
            in_probe = probe_len
            since_probe = 0
        # 决策
        if t < b0:
            rebuild = True
        elif a == 0:
            rebuild = True
        elif in_probe > 0:
            rebuild = False          # 探针期强制复用
        elif a >= amax:
            rebuild = True
        else:
            # 贪心：用已知曲线估计 ΔN(a)
            if a in know:
                dn = know[a]
            elif know:
                ks = sorted(know)
                if len(ks) >= 2:
                    (a1, a2) = ks[-2], ks[-1]
                    sl = (know[a2] - know[a1]) / max(1e-9, a2 - a1)
                    dn = know[a2] + sl * (a - a2)
                else:
                    dn = know[ks[-1]]
            else:
                dn = 45.0 * a
            rebuild = dn > r0
            # 加速检测
            if not rebuild and ratio_thresh is not None and know:
                ks = sorted(know)
                if len(ks) >= 2:
                    a1, a2 = ks[-2], ks[-1]
                    if know[a1] > 1e-9:
                        ratio = know[a2] / know[a1]
                        if ratio >= ratio_thresh:
                            rebuild = True
        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            a = 1
            if n0 is None or True:
                n0 = nn          # 以最近一次重建为基线
            in_probe = min(in_probe, 0) if in_probe == 0 else in_probe
        else:
            nn = Nfn(t, a)
            tot += nn
            if n0 is not None:
                know[a] = nn - n0
            a += 1
            if in_probe > 0:
                in_probe -= 1
        since_probe += 1
    return tot


def sim_dual_baseline(Nfn, r0, b0=100, amax=60):
    """★ 用"最近一次重建时的 N(0)"作基线，并记录 (age, 本次 N) 与 (age, N(0))。
    关键改进：ΔN 用【局部基线】，避免全局中位掩盖时间变化。"""
    know = defaultdict(list)     # age -> [ΔN 观测]
    tot, a = 0.0, 0
    n0 = None
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            n0 = Nfn(t, 0)
            continue
        if a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            if a in know and know[a]:
                dn = st.median(know[a])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a1, a2 = ks[-2], ks[-1]
                    d1, d2 = st.median(know[a1]), st.median(know[a2])
                    sl = (d2 - d1) / max(1e-9, a2 - a1)
                    dn = d2 + sl * (a - a2)
                else:
                    dn = st.median(know[ks[-1]])
            else:
                dn = 45.0 * a
            rebuild = dn > r0
        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            a = 1
            n0 = nn
        else:
            nn = Nfn(t, a)
            tot += nn
            if n0 is not None:
                know[a].append(nn - n0)
            a += 1
    return tot


def report(level, r0):
    print(f"\n{'#'*100}")
    print(f"#  levels = {level}，r = {r0}")
    print(f"{'#'*100}")
    tab = build_table(level)
    Nfn, curve = make_nfn_wrap(tab)
    base = sim_fixed(Nfn, r0, 1)
    orc, orcnr, _ = sim_dp(Nfn, r0)

    print(f"  K=1 基线 {base:.1f}   真 oracle {orc:.1f}   "
          f"离线最优固定周期 {min(sim_fixed(Nfn, r0, K) for K in range(1,13)):.1f}")

    print(f"\n  {'策略':>40} {'代价':>10} {'相对K=1':>9} {'Regret':>9}")
    res = {}

    def show(name, c):
        res[name] = c
        print(f"  {name:>40} {c:>10.1f} {(c/base-1)*100:>8.2f}% "
              f"{(c/orc-1)*100:>8.2f}%")

    # 参照
    print(f"  {'K=1 每步重建':>40} {base:>10.1f} {0.0:>8.2f}% "
          f"{(base/orc-1)*100:>8.2f}%")
    bestK = min(range(1, 13), key=lambda K: sim_fixed(Nfn, r0, K))
    bk = sim_fixed(Nfn, r0, bestK)
    print(f"  {f'K*={bestK} 离线最优固定周期':>40} {bk:>10.1f} "
          f"{(bk/base-1)*100:>8.2f}% {(bk/orc-1)*100:>8.2f}%")
    g0 = sim_greedy_true(Nfn, curve, r0)
    show("G0 贪心 + 真年龄曲线（ceiling）", g0)

    # v2 各变体
    show("G1 贪心 + 在线学习（v1，对照）", sim_greedy_learned(Nfn, r0))
    for pl in (2, 3, 5):
        show(f"V2a 探针{pl}(仅一次) + 贪心",
             sim_probe_greedy(Nfn, r0, probe_len=pl, probe_every=10**9))
    for pl, pe in ((3, 40), (3, 80), (5, 60)):
        show(f"V2a 探针{pl} 每{pe}步 + 贪心",
             sim_probe_greedy(Nfn, r0, probe_len=pl, probe_every=pe))
    for rt in (1.6, 2.0, 2.5):
        show(f"V2b 加速检测 ratio>{rt}",
             sim_probe_greedy(Nfn, r0, probe_len=0, probe_every=10**9,
                              ratio_thresh=rt))
    show("V2c 局部基线 + 贪心", sim_dual_baseline(Nfn, r0))
    for rt in (1.6, 2.0):
        show(f"V2d 局部基线 + ratio>{rt}",
             sim_dual_baseline_ratio(Nfn, r0, rt))

    print(f"  {'真 oracle（不可实现）':>40} {orc:>10.1f} "
          f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")
    return dict(level=level, r=r0, base=base, bestK=bestK, fixed=bk,
                oracle=orc, policies=res)


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


def sim_greedy_true(Nfn, curve, r0, b0=100, amax=80):
    n0 = curve[0]
    tot, a = 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            continue
        if a == 0 or a >= amax:
            rebuild = True
        else:
            rebuild = (curve.get(a, curve[max(curve)]) - n0) > r0
        if rebuild:
            tot += r0 + Nfn(t, 0)
            a = 1
        else:
            tot += Nfn(t, a)
            a += 1
    return tot


def sim_greedy_learned(Nfn, r0, b0=100, amax=40, prior_slope=45.0):
    obs = []
    tot, a = 0.0, 0
    n0 = None
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            n0 = Nfn(t, 0)
            continue
        if a == 0 or a >= amax:
            rebuild = True
        else:
            if obs:
                known = sorted(obs)
                ages = [x[0] for x in known]
                dns = [x[1] for x in known]
                if a in ages:
                    est = dns[ages.index(a)]
                elif len(known) >= 2 and ages[-1] > ages[-2]:
                    sl = (dns[-1] - dns[-2]) / (ages[-1] - ages[-2])
                    est = dns[-1] + sl * (a - ages[-1])
                else:
                    est = dns[-1] + prior_slope * (a - ages[-1])
                est = max(0.0, est)
            else:
                est = prior_slope * a
            rebuild = est > r0
        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            a = 1
            n0 = nn
        else:
            nn = Nfn(t, a)
            tot += nn
            if n0 is not None:
                obs.append((a, nn - n0))
            a += 1
    return tot


def sim_dual_baseline_ratio(Nfn, r0, ratio_thresh, b0=100, amax=60):
    know = defaultdict(list)
    tot, a = 0.0, 0
    n0 = None
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            n0 = Nfn(t, 0)
            continue
        if a == 0 or a >= amax:
            rebuild = True
        else:
            if a in know and know[a]:
                dn = st.median(know[a])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a1, a2 = ks[-2], ks[-1]
                    d1, d2 = st.median(know[a1]), st.median(know[a2])
                    sl = (d2 - d1) / max(1e-9, a2 - a1)
                    dn = d2 + sl * (a - a2)
                else:
                    dn = st.median(know[ks[-1]])
            else:
                dn = 45.0 * a
            rebuild = dn > r0
            if not rebuild and know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a1, a2 = ks[-2], ks[-1]
                    d1, d2 = st.median(know[a1]), st.median(know[a2])
                    if d1 > 1e-9 and d2 / d1 >= ratio_thresh:
                        rebuild = True
        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            a = 1
            n0 = nn
        else:
            nn = Nfn(t, a)
            tot += nn
            if n0 is not None:
                know[a].append(nn - n0)
            a += 1
    return tot


def make_nfn_wrap(tab):
    """与 make_Nfn 相同，改名以避免与其他脚本混淆。"""
    return make_Nfn(tab)


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


def main():
    print("=" * 100)
    print("★★ 在线贪心策略 v2：修补信息缺口")
    print("=" * 100)
    out = []
    for level, r0 in ((5, 35.00), (2, 22.43)):
        d = report(level, r0)
        out.append(d)

    print(f"\n{'='*100}")
    print("★ 汇总：regret（相对真 oracle）")
    print(f"{'='*100}")
    for d in out:
        bK = d["bestK"]
        print("\n  levels=%d（r=%.1f，离线最优 K*=%d）" % (d["level"], d["r"], bK))
        print("    %-34s: %6.2f%%" % ("K=1 每步重建",
                                      (d["base"] / d["oracle"] - 1) * 100))
        print("    %-34s: %6.2f%%" % ("K*=%d 离线最优固定周期" % bK,
                                      (d["fixed"] / d["oracle"] - 1) * 100))
        for k, v in sorted(d["policies"].items(), key=lambda kv: kv[1]):
            tag = " ★" if v < d["fixed"] else ""
            print("    %-34s: %6.2f%%%s" % (k, (v / d["oracle"] - 1) * 100, tag))
        print("    %-34s:   0.00%%" % "真 oracle")

    with open("greedy_v2_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n⇒ 写入 greedy_v2_result.json")


if __name__ == "__main__":
    main()
