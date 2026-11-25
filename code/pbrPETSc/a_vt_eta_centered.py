#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eta 的中心化修正：把与选周期无关的水平平移从 eta 里剔掉。

问题
----
`a_vt_eta.py` 用未归一化的 N 构造
    c_t(K) = mean_{a<K} N(t,a) + rho/K
于是 eta_t = max_K |c_t(K) - c_{t-1}(K)| 含有一个对全部 K 相同的分量（整体水平移动）。
但选周期只看 argmin，**K 无关的平移不改变任何决策**。所以真正决策相关的是

    delta_c(K)  = c_t(K) - c_{t-1}(K)
    delta_c_bar = mean_K delta_c(K)
    eta_c_t     = max_K | delta_c(K) - delta_c_bar |        # 中心化后

同时报水平项 |delta_c_bar|，看 eta 里有多少是这个无关分量。
另报 c 的典型量级，用于把 eta 换算成"能容忍多少步"。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, load_phase  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_eta_c.json")
KMAX = 20


def frames_of(tab):
    ts = sorted({t for (t, _a) in tab})
    as_ = sorted({a for (_t, a) in tab})
    fr = {}
    for t in ts:
        p = {a: tab[(t, a)] for a in as_ if (t, a) in tab}
        if 0 in p and len(p) >= 4:
            fr[t] = p
    return fr


def cvec(p, rho):
    v = {}
    for K in range(1, KMAX + 1):
        ages = [a for a in range(K) if a in p]
        if len(ages) < K:
            break
        v[K] = st.mean(p[a] for a in ages) + rho / K
    return v


def main():
    out = {"kind": "eta_centered", "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                    # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        fr = frames_of(ph["tab"])
        rho = ph.get("r1") or 10.0
        ts = sorted(fr)
        cs = {t: cvec(fr[t], rho) for t in ts}
        cs = {t: v for t, v in cs.items() if len(v) >= 2}

        eta_raw, eta_c, level, cscale, kshift = [], [], [], [], 0
        prev_k = None
        for t0, t1 in zip(sorted(cs), sorted(cs)[1:]):
            v0, v1 = cs[t0], cs[t1]
            common = sorted(set(v0) & set(v1))
            if len(common) < 2:
                continue
            d = {K: v1[K] - v0[K] for K in common}
            dbar = st.mean(d.values())
            eta_raw.append(max(abs(x) for x in d.values()))
            eta_c.append(max(abs(d[K] - dbar) for K in common))
            level.append(abs(dbar))
            cscale.append(st.mean(v1.values()))
            k0 = min(v0, key=v0.get)
            k1 = min(v1, key=v1.get)
            if prev_k is not None and k1 != k0:
                kshift += 1
            prev_k = k1

        e = {"n_frames": len(cs), "rho": rho, "T": ph.get("T"),
             "eta_raw_per_step": round(st.mean(eta_raw), 3) if eta_raw else None,
             "eta_centered_per_step": round(st.mean(eta_c), 3) if eta_c else None,
             "level_per_step": round(st.mean(level), 3) if level else None,
             "frac_level": (round(st.mean(level) / st.mean(eta_raw), 3)
                            if eta_raw and st.mean(eta_raw) else None),
             "c_scale": round(st.mean(cscale), 1) if cscale else None,
             # 容忍跨度：c 的量级相对每步决策相关变差是多少步
             "horizon_steps": (round(st.mean(cscale) / st.mean(eta_c), 1)
                               if eta_c and st.mean(eta_c) else None),
             "n_kshift": kshift}
        out["cases"][tag] = e
        print("%-5s eta_raw=%-7s eta_ctr=%-7s level=%-7s (%.0f%%) c~%-7s horizon=%-7s K*移位=%d"
              % (tag, e["eta_raw_per_step"], e["eta_centered_per_step"],
                 e["level_per_step"], 100 * (e["frac_level"] or 0), e["c_scale"],
                 e["horizon_steps"], e["n_kshift"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
