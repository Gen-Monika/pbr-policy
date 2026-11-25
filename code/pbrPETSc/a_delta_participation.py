#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""老化项 max(0,delta) 在决策中的参与度（OpenFOAM 七配置）。

判定的问题
----------
在低老化宿主（ASPECT/MOOSE 六 trace）上，max(0,delta) 在 98.8% 的决策行为 0，
删掉老化项后决策几乎不变。那么在高老化配置（OpenFOAM 七配置，rho 17–147）
上，老化项是否真正接手？

判据
----
1. 参与率 = max(0,delta)>0 的决策行 / 总决策行
2. 强制 delta=0 后的决策分歧率
若两者都显著高于 ASPECT 的读数（2.8% / 0%），则"老化弱时退化、老化强时接手"成立。

审计边界
--------
* 不改 pbrcost.py 的任何逻辑；只调用 sim_online_detail(trace=True)。
* 不改 rho、B0、K、判据形式。
* 分歧率用同一份观测流重放（delta 置零版另写一个局部副本，仅用于对照），
  不重跑求解器。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import CFG, ORDER, Env, load_phase, sim_online_detail  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_delta_participation.json")


def main():
    out = {"kind": "delta_participation", "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                       # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "load_phase returned None"}
            continue
        tab, rho, B0 = ph["tab"], ph["r1"], ph["B0"]
        sFact = ph.get("s", 3.0)
        env = Env(tab, sFact=sFact)
        T = ph.get("T") or max(t for (t, _a) in tab)

        tr = []
        tot, it, rb, pred, _mv = sim_online_detail(env, rho, T, B0,
                                                   step_cost=True, trace=tr)
        # trace: (t, lhs, avg, margin)；lvl+max(0,delta)=lhs，需要单独拿 delta
        # → 用 lvl 重建：delta = lhs - lvl，lvl 是上一重建步的 N
        # 这里改为直接重跑一遍带 delta 记录的版本
        know = {}; levels = []
        A = 0; acc = 0.0; accn = 0; held = -1; tt = 0.0
        rows = []
        for t in range(1, T + 1):
            rc1 = rho * sFact
            if t < B0 or held < 0 or not levels:
                rebuild = True; age = 0; delta = None; lvl = None; avg = None
            else:
                age = t - held
                avg = acc / accn if accn else tt / max(1, t - 1)
                lvl = levels[-1]
                if age in know and know[age]:
                    delta = st.median(know[age]); src = "hit"
                elif know:
                    ks = sorted(k for k in know if know[k])
                    if len(ks) >= 2:
                        a2, a1 = ks[-1], ks[-2]
                        d2, d1 = st.median(know[a2]), st.median(know[a1])
                        delta = d2 + (d2 - d1) / max(1e-9, a2 - a1) * (age - a2)
                        src = "extrap"
                    else:
                        delta = st.median(know[ks[-1]]); src = "flat"
                else:
                    delta = 0.0; src = "boot"
                rebuild = (lvl + max(0.0, delta)) > avg
            rows.append(dict(t=t, age=age, lvl=lvl, delta=delta, avg=avg,
                             rebuild=int(rebuild), src=(src if lvl is not None else "warmup")))
            if rebuild:
                N = env(t, 0); tt += rc1 + N
                acc, accn = (0.0, 0) if t < B0 else (rc1 + N, 1)
                levels.append(N); held = t
            else:
                N = env(t, age); tt += N
                acc += N; accn += 1
                if levels:
                    bm = st.median(levels)
                    if bm > 1e-9:
                        know.setdefault(age, []).append(N - bm)

        dec = [r for r in rows if r["delta"] is not None]
        pos = [r for r in dec if r["delta"] > 1e-9]
        neg = [r for r in dec if r["delta"] < -1e-9]
        nz = [r for r in dec if abs(r["delta"]) <= 1e-9]

        # 不做"强制 delta=0 重跑"：那会让策略永不重建、年龄无限增长，
        # 外推器随之发散（fx 在 age=245 给出 N≈12989，是 age0 的 520 倍），
        # 得到的成本差是外推器产物，不是策略性能。改为直接分类每次重建的触发者。
        rb_pure = sum(1 for r in dec if r["rebuild"] == 1
                      and r["lvl"] is not None and r["lvl"] > r["avg"])
        rb_delta = sum(1 for r in dec if r["rebuild"] == 1
                       and r["lvl"] is not None and r["lvl"] <= r["avg"]
                       and r["lvl"] + max(0.0, r["delta"]) > r["avg"])
        margins = [(r["lvl"] - r["avg"], r["delta"]) for r in dec if r["rebuild"] == 1]

        out["cases"][tag] = {
            "rho": round(rho, 4), "B0": B0, "T": T, "sFact": round(sFact, 3),
            "n_decisions": len(dec),
            "n_delta_pos": len(pos), "n_delta_neg": len(neg), "n_delta_zero": len(nz),
            "pct_delta_pos": round(100 * len(pos) / len(dec), 1) if dec else None,
            "median_delta": round(st.median([r["delta"] for r in dec]), 2) if dec else None,
            "median_pos_delta": round(st.median([r["delta"] for r in pos]), 2) if pos else None,
            "src_hist": {s: sum(1 for r in dec if r["src"] == s)
                         for s in ("hit", "extrap", "flat", "boot")},
            # 分母必须只含预热后的重建：预热期 t<B0 无条件重建，
            # 那些行没有 delta（dec 已排除），若混进分母会把占比系统性压低。
            "rebuilds_total": rb,
            "rebuilds_warmup": rb - rb_pure - rb_delta,
            "rebuilds_post": rb_pure + rb_delta,
            "rebuilds_lvl_alone": rb_pure,
            "rebuilds_delta_decisive": rb_delta,
            "pct_post_rebuilds_delta_decisive":
                round(100 * rb_delta / (rb_pure + rb_delta), 1) if (rb_pure + rb_delta) else None,
            "median_lvl_minus_avg_at_rebuild":
                round(st.median([m[0] for m in margins]), 1) if margins else None,
            "median_delta_at_rebuild":
                round(st.median([m[1] for m in margins]), 1) if margins else None,
        }
        c = out["cases"][tag]
        print("%-5s rho=%-7.1f 决策 %-5d Δ>0 %-5d (%.1f%%) Δ中位 %+.1f  |  post重建 %-4d"
              "  Δ决定性 %-4d (%.0f%%)  重建时 lvl-avg %+.1f, Δ %+.1f"
              % (tag, c["rho"], c["n_decisions"], c["n_delta_pos"], c["pct_delta_pos"] or 0,
                 c["median_delta"] or 0, c["rebuilds_post"],
                 c["rebuilds_delta_decisive"], c["pct_post_rebuilds_delta_decisive"] or 0,
                 c["median_lvl_minus_avg_at_rebuild"] or 0,
                 c["median_delta_at_rebuild"] or 0))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
