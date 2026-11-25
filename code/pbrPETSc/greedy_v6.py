#!/usr/bin/env python3
"""
★★★ 在线策略 v6：修正探针实现，专攻"信息缺口"

═══════════════════════════════════════════════════════════════════════
为什么必须在 L10 上解决这个问题
═══════════════════════════════════════════════════════════════════════
levels=10 实测：r = 58.06，年龄曲线
    N(0)=22, N(1)=38, N(2)=60, N(3)=84, N(4)=111, N(5)=145, N(6)=198, N(7)=248

  avg 判据的手工推演：
    重建：cost = r + N(0) = 58 + 22 = 80，avg = 80
    a=1：N=38 < 80 ⇒ 复用；tot=118，avg=59
    a=2：N=60 > 59 ⇒ 重建
  ⇒ 自洽周期 = 2 ⇒ 与实测最优 K*=2 一致 ✓

  ⚠️ 但后果：策略几乎只观测到 a=1
     ⇒ 学不到 δ(2)=38、δ(3)=62、δ(4)=89 …
     ⇒ 而 oracle 的重建间隔中位是 4 ⇒ 它用到了 a=2,3
     ⇒ 在线 regret 因此恶化（L5 时 21.78%，L10 时 59.40%）

  ★ 这正是"探索-利用"问题：不主动探针就永远学不到更长的年龄。

═══════════════════════════════════════════════════════════════════════
v2/v3 的探针为什么没生效（两处实现错误）
═══════════════════════════════════════════════════════════════════════
错误1：`in_probe` 的判据放在 `a == 0` 之后 ⇒ 首步重建把 in_probe 清零
错误2：`probe_every` 默认 10**9 ⇒ 探针永不触发

v6 的正确实现：
  - 探针判据排在 `a == 0` 之前
  - 用"是否还需要学习 δ(a)"作为触发条件（而非固定周期）
  - 探针长度自适应：学到足够长的年龄就停止
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
    if level == 10:
        d = "l10"; pre = "l10"
    elif level == 5:
        d = "l5"; pre = "l5"
    else:
        d = None; pre = "s"
    cells = defaultdict(list)
    if d:
        pairs = [(f"{d}/log.k{K}r{R}", f"{pre}_k{K}_r{R}.csv")
                 for K in (1, 2, 3, 4, 5, 6, 8) for R in (1, 2, 3)]
        pairs += [(f"{d}/log.big{R}", f"{pre}_big_r{R}.csv") for R in (1, 2)]
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


def sim_dp(Nfn, r0, AMAX=90):
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


def sim_v6(Nfn, r0, b0=100, amax=90, target_age=0, force_every=0,
           lvl_mode="last", avg_mode="recent"):
    """★ v6：带正确探针的 avg 判据。

    target_age  : 希望学到的最长年龄（0 = 不探针）
    force_every : 距上次探针多少步后允许再探（0 = 只在启动时探一次）
    """
    know = defaultdict(list)
    levels = []
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    in_probe = 0
    steps_since_probe = 10**9
    probes_done = 0

    for t in range(1, T_MAX + 1):
        # ── lvl 估计 ──
        if lvl_mode == "last":
            lvl = levels[-1] if levels else None
        elif lvl_mode == "median16":
            lvl = st.median(levels[-16:]) if levels else None
        else:
            lvl = (levels[-1] + (levels[-1] - levels[-2])
                   if len(levels) >= 2 else (levels[-1] if levels else None))

        # ── 决策（探针优先，排在 a==0 之前！）──
        if t < b0:
            rebuild = True
        elif in_probe > 0:
            rebuild = False                      # ★ 探针期强制复用
        elif a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            avg = (acc / accn) if (avg_mode == "recent" and accn) \
                else (tot / (t - 1))
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

        # ── 执行 ──
        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            acc, accn = r0 + nn, 1
            a = 1
            levels.append(nn)
            steps_since_probe += 1
            # 是否启动探针
            if target_age > 0 and a == 1:
                learned = max([k for k in know if know[k]], default=0)
                if learned < target_age and steps_since_probe >= force_every:
                    in_probe = target_age - learned
                    steps_since_probe = 0
                    probes_done += 1
        else:
            nn = Nfn(t, a)
            tot += nn
            acc += nn
            accn += 1
            if levels:
                bmed = st.median(levels)
                if bmed > 1e-9:
                    know[a].append(nn - bmed)
            a += 1
            if in_probe > 0:
                in_probe -= 1
            steps_since_probe += 1
    return tot, probes_done, max([k for k in know if know[k]], default=0)


def sim_ceiling(Nfn, r0, b0=100, amax=90):
    tot, a, acc, accn = 0.0, 0, 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < b0:
            v = r0 + Nfn(t, 0)
            tot += v
            acc, accn = v, 1
            a = 1
            continue
        avg = acc / accn if accn else tot / (t - 1)
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


def main():
    print("=" * 100)
    print("★★★ 在线策略 v6：修正探针，专攻信息缺口")
    print("=" * 100)

    out = []
    for level, r0 in ((10, 58.06), (5, 35.00)):
        print(f"\n{'#'*100}")
        print(f"#  levels = {level}，r = {r0}")
        print(f"{'#'*100}")
        tab = build_table(level)
        Nfn, curve = make_Nfn(tab)
        base = sim_fixed(Nfn, r0, 1)
        orc, orcnr, orcpath = sim_dp(Nfn, r0)
        fixed = {K: sim_fixed(Nfn, r0, K) for K in range(1, 13)}
        bestK = min(fixed, key=fixed.get)

        print(f"  曲线 N(0..8): " + " ".join(f"{curve.get(a,0):.0f}"
                                               for a in range(9)))
        print(f"  K=1={base:.1f}  K*={bestK}({fixed[bestK]:.1f})  "
              f"oracle={orc:.1f}({orcnr}次重建)")

        print(f"\n  {'策略':>46} {'cost':>10} {'相对K=1':>9} {'Regret':>9} "
              f"{'学到的最大年龄':>14}")
        res = {}

        def show(name, c, learned=None):
            star = " ★" if c < fixed[bestK] else ""
            lm = "" if learned is None else str(learned)
            print(f"  {name:>46} {c:>10.1f} {(c/base-1)*100:>8.2f}% "
                  f"{(c/orc-1)*100:>8.2f}%{star:>2}{lm:>14}")
            res[name] = c

        print(f"  {'K=1 每步重建':>46} {base:>10.1f} {0.0:>8.2f}% "
              f"{(base/orc-1)*100:>8.2f}%")
        print(f"  {f'K*={bestK} 离线最优固定周期':>46} {fixed[bestK]:>10.1f} "
              f"{(fixed[bestK]/base-1)*100:>8.2f}% "
              f"{(fixed[bestK]/orc-1)*100:>8.2f}%")

        cv = sim_ceiling(Nfn, r0)
        show("C0 ceiling（真N(t,a)+avg_recent）", cv)

        # 无探针
        c, p, lm = sim_v6(Nfn, r0, target_age=0)
        show("P0 无探针", c, lm)

        # 探针变体
        for ta in (3, 5, 8, 12):
            c, p, lm = sim_v6(Nfn, r0, target_age=ta, force_every=40)
            show(f"P1 探针至 a={ta}（每 40 步）", c, lm)
        for ta, fe in ((5, 20), (8, 20), (5, 80), (8, 80)):
            c, p, lm = sim_v6(Nfn, r0, target_age=ta, force_every=fe)
            show(f"P2 探针至 a={ta}（每 {fe} 步）", c, lm)

        print(f"  {'真 oracle（不可实现）':>46} {orc:>10.1f} "
              f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")

        out.append(dict(level=level, r=r0, base=base, bestK=bestK,
                        fixed=fixed[bestK], oracle=orc, ceiling=cv,
                        policies=res))

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
        print("    %-40s: %6.2f%%" % ("C0 ceiling", (d["ceiling"] / d["oracle"] - 1) * 100))
        for k, v in sorted(d["policies"].items(), key=lambda kv: kv[1]):
            tag = " ★优于固定周期" if v < d["fixed"] else ""
            print("    %-40s: %6.2f%%%s" % (k, (v / d["oracle"] - 1) * 100, tag))
        print("    %-40s:   0.00%%" % "真 oracle")

    with open("greedy_v6_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n=> 写入 greedy_v6_result.json")


if __name__ == "__main__":
    main()
