#!/usr/bin/env python3
"""
任务 #29（修正版）：把离线最优转为在线策略，并测 regret。

═══════════════════════════════════════════════════════════════════════
相对上一版的两处修正
═══════════════════════════════════════════════════════════════════════
修正 1（致命）：重建分支后 a 应置 1，而不是 0。
    旧版置 0，而判据是 `if a == 0 or pred >= avg` ⇒ 恒真 ⇒ 恒重建，
    导致全部在线策略退化为 K=1 基线。

修正 2（关键）：oracle 的年龄上限不能取小值。
    旧版 amax=12，在 a>=12 时把"复用"置为 INF ⇒ oracle 被上限逼着重建。
    证据：旧版重建间隔中位数恰好 = 13 = amax+1。
    ⇒ 现取 amax=80（远大于任何合理最优年龄），并验证 oracle 的重建
      决策不再卡在上限。

═══════════════════════════════════════════════════════════════════════
数据：N(t, a) 的年龄覆盖
═══════════════════════════════════════════════════════════════════════
 s1..s8 (K=1..8)   : a ∈ [0, 7]      —— 小年龄段，密集
 damBreak_petsc 冻结 @100 永不重建 : a 覆盖 [0, 200+]  —— 大年龄段
  实测形态：N 在 a=0..100 内保持 ~25，随后爆炸
            831(a≈100) → 2510 → 4245 → 5018 → 饱和 ~5300（a≈150 后）

⇒ 两段合起来给出完整的 N(a) 曲线，全部来自实测。
"""
import os
import re
import json
import statistics as st

R = 22.4
STEPS = 344


def load_N(logpath):
    pat = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
    N = []
    if not os.path.exists(logpath):
        return []
    for ln in open(logpath, errors="ignore"):
        if "p_rgh" not in ln:
            continue
        m = pat.search(ln)
        if m:
            N.append(int(m.group(1)))
    return N


# ─────────────────────────────────────────────────────────────────────
# 1. 建 N(t, a) 观测表（全部来自实测）
# ─────────────────────────────────────────────────────────────────────
def build_obs():
    obs = {}   # (t, a) -> [N, ...]

    def add(t, a, v):
        obs.setdefault((t, a), []).append(v)

    # (i) s1..s8：周期 K 给出 a ∈ [0, K-1]
    for K in (1, 2, 3, 4, 5, 6, 8):
        for rep in (1, 2, 3):
            logp, csvp = f"s{K}/log.s{rep}", f"s_k{K}_r{rep}.csv"
            N = load_N(logp)
            if not N or not os.path.exists(csvp):
                continue
            last, i = None, 0
            for ln in open(csvp):
                p = ln.rstrip("\n").split(",")
                if len(p) != 20:
                    continue
                if i >= len(N):
                    break
                t = int(float(p[0]))
                if int(float(p[8])) == 0:      # reused==0 ⇒ 本步重建
                    last = t
                if last is not None:
                    add(t, t - last, N[i])
                i += 1

    # (ii) damBreak_petsc 冻结 @100 永不重建：给出大年龄段
    N = load_N("damBreak_petsc/log.f100")
    csvp = "damBreak_petsc/seq_f100.txt"
    if N:
        # 冻结基准为 100；a = t - 100
        for i, v in enumerate(N):
            t = i + 1                       # seq 按步序编号
            a = t - 100
            if a >= 0:
                add(t, a, v)

    return {k: st.median(v) for k, v in obs.items()}


def build_Nfn(obs):
    """N(t, a)：优先精确命中；否则用同 t 邻近年龄；否则按年龄聚合。"""
    by_t = {}
    by_a = {}
    for (t, a), v in obs.items():
        by_t.setdefault(t, []).append((a, v))
        by_a.setdefault(a, []).append(v)
    age_curve = {a: st.median(v) for a, v in by_a.items()}
    amax_obs = max(age_curve)

    def N(t, a):
        if (t, a) in obs:
            return obs[(t, a)]
        if t in by_t:
            return min(by_t[t], key=lambda p: abs(p[0] - a))[1]
        if a in age_curve:
            return age_curve[a]
        # 年龄超出观测：饱和（实测证实 N 在 a≈150 后饱和）
        return age_curve[amax_obs]

    return N, age_curve, amax_obs


# ─────────────────────────────────────────────────────────────────────
# 2. 策略
# ─────────────────────────────────────────────────────────────────────
def sim_periodic(N, K, T=STEPS):
    """固定周期 K。"""
    total, a, nreb = 0.0, 0, 0
    for t in range(T):
        if a == 0 or a >= K:
            total += R + N(t, 0)
            nreb += 1
            a = 1
        else:
            total += N(t, a)
            a += 1
    return total, nreb


def sim_dp(N, T=STEPS, amax=80):
    """真 oracle：后向 DP，已知全部未来。"""
    INF = float("inf")
    V = [[INF] * (amax + 1) for _ in range(T + 1)]
    act = [[0] * (amax + 1) for _ in range(T + 1)]
    for a in range(amax + 1):
        V[T][a] = 0.0
    for t in range(T - 1, -1, -1):
        for a in range(amax + 1):
            c_reb = R + N(t, 0) + V[t + 1][0]
            c_keep = N(t, a) + V[t + 1][a + 1] if a < amax else INF
            if c_reb <= c_keep:
                V[t][a], act[t][a] = c_reb, 1
            else:
                V[t][a], act[t][a] = c_keep, 0
    total, a, nreb, path = 0.0, 0, 0, []
    for t in range(T):
        if act[t][a] == 1:
            total += R + N(t, 0)
            nreb += 1
            a = 0
            path.append(t)
        else:
            total += N(t, a)
            a += 1
    return total, nreb, path


def sim_online(N, predict, T=STEPS, warm=6, amax=200):
    """★ 在线策略。只看历史。

    判据：续用有益 ⟺ N̂(t, a) < running_average
          running_average = 累计总代价 / 已走步数
    """
    total, a, nreb = 0.0, 0, 0
    hist = []
    for t in range(T):
        if t < warm:
            total += R + N(t, 0)
            nreb += 1
            a = 1
            hist.append(N(t, 0))
            continue
        avg = total / t
        pred = predict(hist, a, t, N)
        if a >= amax or pred >= avg:
            total += R + N(t, 0)
            nreb += 1
            a = 1
            hist.append(N(t, 0))
        else:
            total += N(t, a)
            a += 1
            hist.append(N(t, a))
    return total, nreb


def pred_persist(hist, a, t, N):
    return hist[-1]


def pred_trend(hist, a, t, N):
    if len(hist) < 4:
        return hist[-1]
    d = st.mean([hist[-1] - hist[-2], hist[-2] - hist[-3], hist[-3] - hist[-4]])
    return max(1.0, hist[-1] + d * max(1, a))


def pred_tail(hist, a, t, N):
    if len(hist) < 8:
        return hist[-1]
    w = hist[-32:] if len(hist) >= 32 else hist
    s = sorted(w)
    return s[int(0.9 * (len(s) - 1))]


def pred_mean(hist, a, t, N):
    w = hist[-16:] if len(hist) >= 16 else hist
    return st.mean(w)


def sim_threshold(N, A, T=STEPS):
    total, a, nreb = 0.0, 0, 0
    for t in range(T):
        if a == 0 or a >= A:
            total += R + N(t, 0)
            nreb += 1
            a = 1
        else:
            total += N(t, a)
            a += 1
    return total, nreb


# ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 90)
    print("任务 #29（修正版）：在线重建策略 vs 真 oracle")
    print("=" * 90)

    obs = build_obs()
    N, age_curve, amax_obs = build_Nfn(obs)
    print(f"\n观测点 {len(obs)} 个；年龄覆盖 a ∈ [0, {amax_obs}]")
    print(f"\n  ★ 年龄曲线 N(a)（实测定中位）—— 分段显示")
    print(f"  {'a':>5} {'N(a)':>10}")
    for a in list(range(0, 16)) + [20, 30, 40, 50, 60, 70, 80, 100, 120, 150, 180, 200]:
        if a in age_curve:
            print(f"  {a:>5} {age_curve[a]:>10.2f}")

    # ── (A) 固定周期 ──
    print("\n" + "=" * 90)
    print("(A) 固定周期 K")
    print("=" * 90)
    per = {}
    for K in range(1, 31):
        c, nr = sim_periodic(N, K)
        per[K] = c
    b1 = per[1]
    print(f"  {'K':>3} {'代价':>10} {'重建':>6} {'相对K=1':>10}")
    for K in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30]:
        print(f"  {K:>3} {per[K]:>10.1f} {344//K if K>0 else 0:>6} "
              f"{(per[K]/b1-1)*100:>9.2f}%")
    bestK = min(per, key=per.get)
    print(f"\n  ⇒ 固定周期最优 K* = {bestK}（代价 {per[bestK]:.1f}，"
          f"相对 K=1 {(per[bestK]/b1-1)*100:+.2f}%）")

    # ── (B) oracle ──
    print("\n" + "=" * 90)
    print("(B) ★ 真 oracle（后向 DP，amax=80，不受上限约束）")
    print("=" * 90)
    dp, dpnr, dppath = sim_dp(N)
    gaps = [b - a for a, b in zip(dppath, dppath[1:])]
    print(f"  代价 {dp:.1f}  重建 {dpnr}  相对 K=1 {(dp/b1-1)*100:+.2f}%")
    print(f"  重建间隔：中位 {st.median(gaps):.0f}  均值 {st.mean(gaps):.2f}  "
          f"范围 [{min(gaps)}, {max(gaps)}]")
    print(f"  重建时刻（前 20）: {dppath[:20]}")
    print(f"  ⚠️ 检查：间隔中位 {st.median(gaps):.0f} 是否等于 amax+1=81"
          f"（若是则仍被上限约束）")
    print(f"     {'未受上限约束 ✓' if st.median(gaps) < 70 else '仍受上限约束 ✗'}")

    # ── (C) 在线 ──
    print("\n" + "=" * 90)
    print("(C) ★★ 在线策略（只看历史，warm=6）")
    print("=" * 90)
    preds = [("persist 上一值", pred_persist),
             ("trend 趋势外推", pred_trend),
             ("mean16 近窗均值", pred_mean),
             ("★ tail p90 尾部", pred_tail)]
    print(f"  {'策略':>20} {'代价':>10} {'重建':>6} {'相对K=1':>9} "
          f"{'相对K*':>9} {'Regret vs oracle':>17}")
    on = {}
    for name, pf in preds:
        c, nr = sim_online(N, pf)
        on[name] = c
        print(f"  {name:>20} {c:>10.1f} {nr:>6} {(c/b1-1)*100:>8.2f}% "
              f"{(c/per[bestK]-1)*100:>8.2f}% {(c/dp-1)*100:>16.2f}%")

    # ── (D) 年龄阈值 ──
    print("\n" + "=" * 90)
    print("(D) 固定年龄阈值 A")
    print("=" * 90)
    th = {}
    for A in range(1, 41):
        c, _ = sim_threshold(N, A)
        th[A] = c
    bestA = min(th, key=th.get)
    print(f"  {'A':>3} {'代价':>10} {'相对K=1':>10}")
    for A in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40]:
        print(f"  {A:>3} {th[A]:>10.1f} {(th[A]/b1-1)*100:>9.2f}%")
    print(f"\n  ⇒ 最优阈值 A* = {bestA}（代价 {th[bestA]:.1f}）")

    # ── (E) 总结 ──
    print("\n" + "=" * 90)
    print("★ 总结：各层次相对 oracle 的 regret")
    print("=" * 90)
    print(f"  {'策略':>32} {'代价':>10} {'Regret':>10} {'占oracle':>10} {'相对K=1':>10}")
    rows = [("K=1 每步重建（默认做法）", per[1]),
            (f"K*={bestK} 固定周期（离线最优）", per[bestK]),
            (f"A*={bestA} 固定年龄阈值", th[bestA])]
    for n_, c in rows:
        print(f"  {n_:>32} {c:>10.1f} {(c/dp-1)*100:>9.2f}% {c/dp*100:>9.2f}% "
              f"{(c/b1-1)*100:>9.2f}%")
    for n_, c in on.items():
        print(f"  {n_:>32} {c:>10.1f} {(c/dp-1)*100:>9.2f}% {c/dp*100:>9.2f}% "
              f"{(c/b1-1)*100:>9.2f}%")
    print(f"  {'真 oracle（不可实现）':>32} {dp:>10.1f} {0.0:>9.2f}% "
          f"{100.0:>9.2f}% {(dp/b1-1)*100:>9.2f}%")

    with open("online_policy_result.json", "w") as f:
        json.dump(dict(R=R, periodic={str(k): v for k, v in per.items()},
                       bestK=bestK, threshold={str(k): v for k, v in th.items()},
                       bestA=bestA, oracle=dp, oracle_nreb=dpnr,
                       oracle_path=dppath, online=on), f, indent=1)
    print("\n⇒ 结果写入 online_policy_result.json")


if __name__ == "__main__":
    main()
