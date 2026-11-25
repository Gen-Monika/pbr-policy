#!/usr/bin/env python3
"""
★★★ 在线策略 v3：用正确的判据形式

═══════════════════════════════════════════════════════════════════════
v2 全线退化为 K=1 的原因（判据方向错了）
═══════════════════════════════════════════════════════════════════════
levels=5 实测：r = 35，N_step(0) = 42，N_step(1) = 59

  v2 用的判据：重建 ⟺ ΔN(a) > r
      at a=1: ΔN = 17，17 > 35 为假 ⇒ 复用（看似对）
      但 fallback 的 45·a 在 a=1 时给 45 > 35 ⇒ 重建 ⇒ 退化为 K=1

  更根本的错误：ΔN 是与 r 比，但 r 不是"该不该复用"的正确基准。

═══════════════════════════════════════════════════════════════════════
正确的判据（由 cost(K) 的一阶最优条件导出）
═══════════════════════════════════════════════════════════════════════
每步决策的正确形式：

    重建该步代价 = r + N(t, 0)
    复用该步代价 =       N(t, a)

  但必须与"整体平均"比较，因为决策是序列性的。设
      avg = 迄今的每步平均代价 = 累计总代价 / 已走步数
  则【复用有益 ⟺ N(t, a) < avg】

  直觉：若"继续用旧预条件子"这一步的代价低于迄今为止的平均水平，
        那就该继续用；否则说明它已经拖后腿，该重建。

验算（levels=5）：
    t=b0 刚重建：total = 77，走 1 步，avg = 77
    下一步 a=1：N = 59 < 77 ⇒ 复用 ✓（正确！）
    再下一步 a=2：N = 80 > avg（此时 total=136, 2 步, avg=68）
                  ⇒ 80 > 68 ⇒ 重建 ✓
    ⇒ 周期约 2，与离线最优 K*=2 一致 ✓

═══════════════════════════════════════════════════════════════════════
在线版本需要学的是 N(t, a) 本身（不是 ΔN）
═══════════════════════════════════════════════════════════════════════
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


# ─────────────────────────────────────────────────────────────────────
# v3 策略
# ─────────────────────────────────────────────────────────────────────
def sim_avgcost_exact(Nfn, r0, b0=100, amax=80):
    """★ 用【真实】N(t,a) 的 avg 判据 —— 该策略族的 ceiling。

    重建 ⟺ N(t, a) > avg，其中 avg = 迄今累计代价 / 已走步数
    """
    tot, a = 0.0, 0
    for t in range(1, T_MAX + 1):
        if t < b0:
            tot += r0 + Nfn(t, 0)
            a = 1
            continue
        avg = tot / (t - 1)
        if a == 0 or a >= amax or Nfn(t, a) > avg:
            tot += r0 + Nfn(t, 0)
            a = 1
        else:
            tot += Nfn(t, a)
            a += 1
    return tot


def sim_avgcost_online(Nfn, r0, b0=100, amax=80, probe_len=0,
                       probe_every=10**9, prior=45.0):
    """★★ 真正可实现的在线版本：N(t,a) 用历史学习。

    学习对象：curve[a] ≈ N_step(a)（"年龄 a 时的每步代价"），
             以及 ratio[t] = N_step(0) 随时间的水平。
    预测：N̂(t, a) = curve_ratio[a] · level_now
          curve_ratio[a] = N(a) / N(0) （无量纲，比绝对值更稳）
          level_now = 最近若干次重建时观测到的 N(0)
    """
    know = defaultdict(list)     # a -> [ N(a)/N(0) 观测 ]
    levels = []                  # 最近观测到的 N(0)
    tot, a = 0.0, 0
    in_probe = 0
    since = 0
    for t in range(1, T_MAX + 1):
        if t >= b0 and since >= probe_every and in_probe == 0 and a == 0:
            in_probe = probe_len
            since = 0

        # 估计当前 N(0) 水平
        if levels:
            lvl = st.median(levels[-16:])
        else:
            lvl = None

        if t < b0:
            rebuild = True
        elif in_probe > 0:
            rebuild = False          # ★ 探针期优先，必须在 a==0 之前判断
        elif a == 0:
            rebuild = True
        elif a >= amax:
            rebuild = True
        else:
            avg = tot / (t - 1)
            if lvl is None:
                est = prior * a
            else:
                # ★ 学【加性增量】δ(a) = N(a) − N(0)，而非比值
                #    理由：比值法在 N(a) 爆炸时会产生巨大放大误差；
                #    加性增量在 a=1..7 的线性段最稳定。
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
                    delta = 0.35 * lvl * a
                est = lvl + max(0.0, delta)
            rebuild = est > avg

        if rebuild:
            nn = Nfn(t, 0)
            tot += r0 + nn
            a = 1
            levels.append(nn)
        else:
            nn = Nfn(t, a)
            tot += nn
            if levels:
                base_lvl = st.median(levels)
                if base_lvl > 1e-9:
                    know[a].append(nn - base_lvl)      # ★ 存加性增量
            a += 1
            if in_probe > 0:
                in_probe -= 1
        since += 1
    return tot


def main():
    print("=" * 100)
    print("★★★ 在线策略 v3：正确的 avg 判据")
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

        print(f"  年龄曲线（a=0..10）: "
              + " ".join(f"{curve.get(a, 0):.0f}" for a in range(11)))

        print(f"\n  {'策略':>40} {'代价':>10} {'相对K=1':>9} {'Regret':>9}")
        res = {}

        def show(name, c):
            res[name] = c
            star = " ★" if c < fixed[bestK] else ""
            print(f"  {name:>40} {c:>10.1f} {(c/base-1)*100:>8.2f}% "
                  f"{(c/orc-1)*100:>8.2f}%{star}")

        print(f"  {'K=1 每步重建':>40} {base:>10.1f} {0.0:>8.2f}% "
              f"{(base/orc-1)*100:>8.2f}%")
        print(f"  {f'K*={bestK} 离线最优固定周期':>40} {fixed[bestK]:>10.1f} "
              f"{(fixed[bestK]/base-1)*100:>8.2f}% "
              f"{(fixed[bestK]/orc-1)*100:>8.2f}%")

        # ceiling
        ce = sim_avgcost_exact(Nfn, r0)
        show("★ C0 avg判据 + 真N(t,a)（ceiling）", ce)

        # 在线
        show("C1 avg判据 + 在线学习（无探针）",
             sim_avgcost_online(Nfn, r0))
        for pl in (2, 3, 5):
            show(f"C2 探针{pl} + avg判据",
                 sim_avgcost_online(Nfn, r0, probe_len=pl))
        for pl, pe in ((3, 60), (3, 120)):
            show(f"C3 探针{pl} 每{pe}步 + avg判据",
                 sim_avgcost_online(Nfn, r0, probe_len=pl, probe_every=pe))

        print(f"  {'真 oracle（不可实现）':>40} {orc:>10.1f} "
              f"{(orc/base-1)*100:>8.2f}% {0.0:>8.2f}%")

        # ceiling 的重建周期
        tot2, a2, iv, last = 0.0, 0, [], None
        for t in range(1, T_MAX + 1):
            if t < 100:
                rb = True
            else:
                avg = tot2 / (t - 1)
                rb = (a2 == 0 or a2 >= 80 or Nfn(t, a2) > avg)
            if rb:
                if last is not None:
                    iv.append(t - last)
                last = t
                tot2 += r0 + Nfn(t, 0)
                a2 = 1
            else:
                tot2 += Nfn(t, a2)
                a2 += 1
        post = [x for x in iv if x > 0]
        print(f"\n  C0 的重建间隔：中位 {st.median(post):.0f}，"
              f"范围 [{min(post)}, {max(post)}]")
        print(f"  oracle 重建 {orcnr} 次，间隔中位 "
              f"{st.median([y-x for x,y in zip(orcpath, orcpath[1:])]):.0f}")

        out.append(dict(level=level, r=r0, base=base, bestK=bestK,
                        fixed=fixed[bestK], oracle=orc, policies=res))

    print(f"\n{'='*100}")
    print("★ 汇总")
    print(f"{'='*100}")
    for d in out:
        bK = d["bestK"]
        print("\n  levels=%d（r=%.1f，离线最优 K*=%d）"
              % (d["level"], d["r"], bK))
        print("    %-36s: %6.2f%%" % ("K=1 每步重建",
                                      (d["base"] / d["oracle"] - 1) * 100))
        print("    %-36s: %6.2f%%" % ("K*=%d 离线最优固定周期" % bK,
                                      (d["fixed"] / d["oracle"] - 1) * 100))
        for k, v in sorted(d["policies"].items(), key=lambda kv: kv[1]):
            tag = " ★优于固定周期" if v < d["fixed"] else ""
            print("    %-36s: %6.2f%%%s" % (k, (v / d["oracle"] - 1) * 100, tag))
        print("    %-36s:   0.00%%" % "真 oracle")

    with open("greedy_v3_result.json", "w") as f:
        json.dump(out, f, indent=1)
    print("\n⇒ 写入 greedy_v3_result.json")


if __name__ == "__main__":
    main()
