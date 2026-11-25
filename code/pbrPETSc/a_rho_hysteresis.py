#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两个候选改动的收益上界：① ρ 精度值多少钱 ② 判据滞回带。

重要更正（本轮查证）
--------------------
原设想 H1 是"把 ρ 从预热期一次性标定改为持续在线更新"。**但生产代码已经在做这件事**：
`pbr_policy.h` 在每次重建步执行 `S.rMed = medianOf(S.rSamples)`，
而 `noteRatio()` 把每次重建的实测 r 推入 `rSamples`。所以 H1 不是新贡献，
它是现状。`pbrcost.py` 里固定的 `rho` 参数只是模拟器的简化。

因此 H1 改成有意义的问题：**ρ 的精度值多少钱？** 这界定了任何"更好的 ρ 估计"
（在线更新、更好的标定、区间化）能买到的上限。若在 ±15% 的 ρ 偏差内成本几乎不动，
则整条"ρ 精度"路线都不值钱。

H2 不变：判据改为 `lvl + max(0,delta) > avg*(1+m)`。
若最优 m 恒为 0，滞回带方向退出。

口径
----
* 基准：`sim_online_detail(env, rho_r1, T, B0, step_cost=True)`。
* 成本 = Σits + ρ·重建数。收益相对基准成本。
* **必须用相位表**：trace 上的反事实无效（改判据不改变已实现 its，
  成本恒等式退化为只数重建次数）。
* 复制的决策循环与 `sim_online_detail` 逐行同构，唯一改动是 margin；
  已由 base 分支（margin=0）与官方函数对账。

审计边界
--------
不改 pbrcost.py、不改论文、不跑求解器、不改 B0 与判据形式。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, Env, load_phase, sim_online_detail  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_rho_hysteresis.json")
BANDS = (0.0, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30)
RHO_K = (0.6, 0.7, 0.8, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.5, 2.0)


def sim(env, rho, T, B0, margin=0.0, rho_eval=None):
    """sim_online_detail 的逐行同构副本，唯一改动是判据加 margin。

    rho        —— 策略内部使用、也进入 avg 的 ρ（决定重建成本怎么计）
    rho_eval   —— 若给出，则最终成本用这个 ρ 重新计价。**必须用它来做 ρ 偏置扫描**：
                  否则降低 ρ 会同时降低分母，读数变成"改账本"而不是"改决策"。
    """
    re_ = rho_eval if rho_eval is not None else rho
    know = {}
    levels = []
    it = 0.0
    rb = 0
    a = 0
    acc = 0.0
    accn = 0
    held = -1
    tot = 0.0
    for t in range(1, T + 1):
        rc1 = rho * env.sFact
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc / accn if accn else tot / max(1, t - 1)
            lvl = levels[-1]
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2 - d1) / max(1e-9, a2 - a1) * (age - a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg * (1.0 + margin)
        if rebuild:
            N = env(t, 0)
            it += N
            rb += 1
            tot += rc1 + N
            acc, accn = (0.0, 0) if t < B0 else (rc1 + N, 1)
            levels.append(N)
            a = 1
            held = t
        else:
            N = env(t, a)
            it += N
            tot += N
            acc += N
            accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9:
                    know.setdefault(a, []).append(N - bm)
            a += 1
    if rho_eval is not None:
        tot = it + re_ * env.sFact * rb
    return tot, it, rb


def main():
    out = {"kind": "rho_precision_and_hysteresis",
           "correction": "生产代码已在每次重建步更新 rMed；H1 改问 ρ 精度值多少钱",
           "bands": list(BANDS), "rho_k": list(RHO_K), "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                     # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        tab, rho, B0, T = ph["tab"], ph["r1"], ph["B0"], ph["T"]
        env = Env(tab, sFact=ph["s"])

        c_base, it_base, rb_base, _p, _m = sim_online_detail(
            env, rho, T, B0, step_cost=True)
        c_repl, _, rb_repl = sim(env, rho, T, B0, margin=0.0)
        # 对账：副本必须与官方一致，否则后面的 margin 读数不可信
        reconcile = abs(c_repl - c_base) < 1e-6 and rb_repl == rb_base

        band = {}
        for m in BANDS:
            c, _, rb_ = sim(env, rho, T, B0, margin=m)
            band[str(m)] = {"cost": round(c, 1), "rebuilds": rb_,
                            "change_pct": round(100 * (c - c_base) / c_base, 3)}

        rho_sw = {}
        for k in RHO_K:
            # 策略用 ρ·k 决策，但**用真实 ρ 计价**，否则读数只是改分母
            c, _, rb_ = sim(env, rho * k, T, B0, rho_eval=rho)
            rho_sw[str(k)] = {"cost": round(c, 1), "rebuilds": rb_,
                              "change_pct": round(100 * (c - c_base) / c_base, 3)}

        best_m = min(band, key=lambda kk: band[kk]["cost"])
        out["cases"][tag] = {
            "rho": round(rho, 4), "B0": B0, "T": T, "sFact": round(ph["s"], 3),
            "base": {"cost": round(c_base, 1), "iters": round(it_base, 1),
                     "rebuilds": rb_base},
            "reconcile_with_official": reconcile,
            "hysteresis": band, "best_hysteresis": best_m,
            "rho_bias_sweep": rho_sw,
        }
        print("%-5s base=%9.0f rb=%-4d 对账=%s | 最优带 m=%-5s %+.3f%% | "
              "ρ×0.8:%+.2f%% ρ×1.2:%+.2f%% ρ×1.5:%+.2f%%"
              % (tag, c_base, rb_base, "OK" if reconcile else "FAIL",
                 best_m, band[best_m]["change_pct"],
                 rho_sw["0.8"]["change_pct"], rho_sw["1.2"]["change_pct"],
                 rho_sw["1.5"]["change_pct"]))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
