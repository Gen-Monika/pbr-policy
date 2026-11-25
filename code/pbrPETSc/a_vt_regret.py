#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向二闸门：是否存在「识别失败且遗憾不可忽略」的算例。

要判定的句子
------------
在现有相位表上，若在预热结束时锁定一个固定周期 K^(t0)、此后永不更新，
相对逐帧最优 K*(t) 的累计遗憾，是否能达到总成本的 1% 以上？
（能 → 存在可当对照的算例；不能 → "识别失败无害"只在弱形式下成立。）

审计边界（本轮不动的东西）
--------------------------
* K* 的定义：c_t(K) = mean_{a<K} N(t,a) + rho/K，argmin over K=1..Kmax。与
  `a_vt_decomp.kstar_track` 逐字一致，连 kmax 默认值都不改。
* rho：用 load_phase 的 r1（实测中位），不接受手填。
* 成本口径：cost = iters + rho*rbsteps（pbrcost 的唯一定义）。
* 不做新求解器运行；不注入合成漂移（那是方向三）；不改任何论文数字。
* 有意的口径差异：这里按**帧均摊成本**逐帧累加，而不是跑 sim_fixed 的
  逐步状态机。原因见下（"为什么不直接跑 sim_fixed"）。

为什么不直接跑 sim_fixed
-------------------------
sim_fixed 在 age > age_max 时要外推 N(t,a)（Env.__call__ 的线性外推），
而本表 age 只到 6。K=7 的固定策略第一轮就要外推到 age 7，外推误差会混进
"遗憾"，把闸门变成一个关于外推质量的问题。所以本闸门在**完全观测的格子**上
算：只取 ages 0..K-1 全部有观测的帧，K <= Kmax=7。

判读时的两个必读限制
--------------------
1. **Kmax=7 是扫描设计（A=6,K=7），不是自然上界。** 若某帧的 argmin 顶在 7，
   那是"扫描上限"不是"最优"，必须单列，不能算作识别失败。
2. 累计遗憾 / 总成本 的两个分母都报：oracle 总成本（逐帧最优）与固定策略
   自身总成本。前者回答"损失有多大"，后者回答"省下的代价有多少被吃掉"。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import CFG, ORDER, load_phase  # noqa: E402

KMAX = 7          # 与相位扫描的 K=7 一致；不要为了"看得更远"而放大
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_regret.json")
# 预热窗口的候选口径：用前 M 帧估 K^，M=B0（策略口径）为主，另两个做敏感性
EST_WINDOWS = ("B0", "100", "half")


def frame_costs(tab, t, kmax=KMAX):
    """给定帧 t，返回 {K: c_t(K)}，只含 ages 0..K-1 全部有观测的 K。"""
    out = {}
    for K in range(1, kmax + 1):
        ages = list(range(K))
        vals = [tab.get((t, a)) for a in ages]
        if any(v is None for v in vals):
            break
        out[K] = st.mean(vals)
    return out


def argmin_k(costs, rho):
    """c_t(K) = mean_{a<K} N(t,a) + rho/K 的 argmin；平局取小 K（与 kstar_track 一致）。"""
    best = None
    bk = None
    for K in sorted(costs):
        c = costs[K] + rho / K
        if best is None or c < best:
            best, bk = c, K
    return bk, best


def estimate_k0(per_frame, frames_est, rho):
    """预热窗口内按时间平均成本最小的固定 K。"""
    tot = {}
    for K in range(1, KMAX + 1):
        vals = []
        for t in frames_est:
            c = per_frame.get(t, {}).get(K)
            if c is not None:
                vals.append(c + rho / K)
        if vals:
            tot[K] = st.mean(vals)
    if not tot:
        return None
    best = min(tot.values())
    for K in sorted(tot):
        if tot[K] == best:
            return K
    return None


def windows_argmax(regrets, win):
    """找累计遗憾最大的连续窗口（长度 win 帧），返回 (起, 止, 累计)。"""
    if len(regrets) < win:
        return None
    ts = sorted(regrets)
    best = None
    run = sum(regrets[t] for t in ts[:win])
    bk = (ts[0], ts[win - 1], run)
    best = bk
    for i in range(win, len(ts)):
        run += regrets[ts[i]] - regrets[ts[i - win]]
        if run > best[2]:
            best = (ts[i - win + 1], ts[i], run)
    return best


def main():
    out = {"kind": "VT_regret_gate", "P2": P2, "kmax": KMAX,
           "premise": "锁定 K^(t0) 不更新，相对逐帧 K*(t) 的累计遗憾是否 >= 1% 总成本",
           "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                          # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        tab, rho, B0 = ph["tab"], ph["r1"], ph["B0"]
        ts = sorted({t for (t, _a) in tab})

        # 逐帧：观测到的 c_t(K) 与逐帧最优
        per_frame = {t: frame_costs(tab, t) for t in ts}
        usable = [t for t in ts if per_frame[t]]
        kstar, cstar = {}, {}
        for t in usable:
            k, c = argmin_k(per_frame[t], rho)
            kstar[t], cstar[t] = k, c
        censor = sum(1 for t in usable if kstar[t] == KMAX)

        entry = {"rho": round(rho, 4), "B0": B0, "T": ph.get("T"),
                 "n_frames": len(ts), "n_usable": len(usable),
                 "t_first_usable": usable[0] if usable else None,
                 "kstar_hist": {str(K): sum(1 for t in usable if kstar[t] == K)
                                for K in range(1, KMAX + 1)},
                 "n_at_scan_ceiling": censor,
                 "est": {}}

        for mode in EST_WINDOWS:
            if mode == "B0":
                cut = B0
            elif mode == "100":
                cut = 100
            else:
                cut = usable[0] + (usable[-1] - usable[0]) // 2
            frames_est = [t for t in usable if t <= cut]
            if len(frames_est) < 3:
                entry["est"][mode] = {"error": "too few frames", "n": len(frames_est)}
                continue
            k0 = estimate_k0(per_frame, frames_est, mode and rho)
            frames_eval = [t for t in usable if t > cut]
            if not frames_eval or k0 is None:
                entry["est"][mode] = {"error": "no eval frames or no k0"}
                continue

            reg, tot_or, tot_fix = {}, 0.0, 0.0
            agree = 0
            for t in frames_eval:
                c_fix = per_frame[t].get(k0)
                if c_fix is None:            # 固定 K 超出该帧的观测范围
                    continue
                c_or = cstar[t]
                r = (c_fix + rho / k0) - c_or
                reg[t] = r
                tot_or += c_or
                tot_fix += c_fix + rho / k0
                if kstar[t] == k0:
                    agree += 1
            if not reg:
                entry["est"][mode] = {"error": "fixed K unobservable in eval frames"}
                continue
            tot_r = sum(reg.values())
            win_len = max(10, len(reg) // 10)
            worst = windows_argmax(reg, win_len)
            entry["est"][mode] = {
                "k0": k0, "cut": cut,
                "n_eval": len(reg), "agree_frac": round(agree / len(reg), 4),
                "regret_total": round(tot_r, 2),
                "cost_oracle": round(tot_or, 2),
                "cost_fixed": round(tot_fix, 2),
                "regret_over_oracle_pct": round(100 * tot_r / tot_or, 4) if tot_or else None,
                "regret_over_fixed_pct": round(100 * tot_r / tot_fix, 4) if tot_fix else None,
                "regret_max_single": round(max(reg.values()), 4),
                "regret_signed_frac_pos": round(
                    sum(1 for v in reg.values() if v > 0) / len(reg), 4),
                "worst_window": ({"t0": worst[0], "t1": worst[1],
                                  "sum": round(worst[2], 2),
                                  "pct_of_window_oracle": None} if worst else None),
            }
            # 该窗口内 oracle 成本，给"窗口内损失占比"
            if worst:
                w_or = sum(cstar[t] for t in reg if worst[0] <= t <= worst[1])
                entry["est"][mode]["worst_window"]["pct_of_window_oracle"] = (
                    round(100 * worst[2] / w_or, 4) if w_or else None)
        out["cases"][tag] = entry
        e = entry["est"].get("B0", {})
        print("%-5s usable=%-5d ceil=%-4d K0=%-2s agree=%-6s regret/oracle=%-8s regret/fixed=%-8s worst_win=%s%%"
              % (tag, entry["n_usable"], censor, e.get("k0"), e.get("agree_frac"),
                 e.get("regret_over_oracle_pct"), e.get("regret_over_fixed_pct"),
                 (e.get("worst_window") or {}).get("pct_of_window_oracle")))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
