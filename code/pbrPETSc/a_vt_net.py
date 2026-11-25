#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向 A 闸门（净位移版）：V_T 是累积变差，会把来回抖动全算成漂移。

为什么必须再测一次
------------------
`a_vt_decomp.py` 报的 D 是窗口均值之间的**累积**变差：窗口均值来回摆动时，
每一步摆动都被累加。但"标定多久失效"取决于窗口均值的**净位移**，不是累积路程。

举例：m 在 100±5 之间来回抖动 200 次，累积变差很大，净位移却是 0，
标定的 K* 一直有效。反之，m 单向从 100 漂到 130，累积与净位移相当，
K* 一定失效。这两种情形在 V_T 上不可区分，必须分开测。

指标
----
    net = max_a | m_last(a) - m_first(a) | / (t_last - t_first)    # 每步净漂移
    D/W                                                             # 每步累积变差（对照）
    ratio = net / (D/W)                                             # ≈0 抖动主导；≈1 单向漂移

另测**形状是否只是被平移**：若 m_last(a) ≈ m_first(a + s)，说明漂移等价于"有效年龄
整体前移 s 步"，这是一个强结构（比任意形状变化好处理得多）。对整数 s 做拟合，报最佳 s 与残差。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, load_phase  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_net.json")
WIDTHS = (50, 100, 200)


def frames_of(tab):
    ts = sorted({t for (t, _a) in tab})
    as_ = sorted({a for (_t, a) in tab})
    fr = {}
    for t in ts:
        p = {a: tab[(t, a)] for a in as_ if (t, a) in tab}
        if 0 in p and len(p) >= 4:
            fr[t] = p
    return fr


def gvec(p):
    return {a: p[a] - p[0] for a in p if a > 0}


def window_means(fr, W):
    ts = sorted(fr)
    out = []
    for i in range(0, len(ts), W):
        chunk = ts[i:i + W]
        if len(chunk) < max(5, W // 3):
            continue
        gs = [gvec(fr[t]) for t in chunk]
        common = set(gs[0])
        for g in gs[1:]:
            common &= set(g)
        common = sorted(common)
        if not common:
            continue
        m = {a: st.mean(g[a] for g in gs) for a in common}
        out.append((st.mean(chunk), m, len(chunk)))
    return out


def cum_var(means):
    d = 0.0
    for (t0, m0, _), (t1, m1, _) in zip(means, means[1:]):
        common = sorted(set(m0) & set(m1))
        if common:
            d += max(abs(m1[a] - m0[a]) for a in common)
    return d


def net_disp(means):
    if len(means) < 2:
        return None
    (t0, m0, _), (t1, m1, _) = means[0], means[-1]
    common = sorted(set(m0) & set(m1))
    if not common:
        return None
    return max(abs(m1[a] - m0[a]) for a in common), (t1 - t0)


def shift_fit(m0, m1, smax=8):
    """m1(a) ≈ m0(a+s) 的最佳整数 s 与相对残差。"""
    best = None
    denom = max(1e-9, max(abs(v) for v in m1.values()))
    for s in range(0, smax + 1):
        pairs = [(m0[a + s], m1[a]) for a in sorted(m1) if (a + s) in m0]
        if len(pairs) < 3:
            continue
        err = st.mean(abs(x - y) for x, y in pairs) / denom
        if best is None or err < best[1]:
            best = (s, err)
    return best


def main():
    out = {"kind": "VT_net_displacement", "P2": P2, "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                       # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        fr = frames_of(ph["tab"])
        entry = {"n_frames": len(fr), "rho": ph.get("r1"), "T": ph.get("T"), "windows": {}}
        for W in WIDTHS:
            means = window_means(fr, W)
            if len(means) < 2:
                continue
            cv = cum_var(means)
            nd = net_disp(means)
            nwin = len(means)
            entry["windows"][str(W)] = {
                "n_win": nwin,
                "cum_per_step": round(cv / (nwin - 1) / W, 5),
                "net_per_step": round(nd[0] / nd[1], 5) if nd else None,
                "net_total": round(nd[0], 2) if nd else None,
                "span": nd[1] if nd else None,
                "ratio_net_over_cum": (round((nd[0] / nd[1]) / (cv / (nwin - 1) / W), 3)
                                       if nd and cv else None),
                "shift": shift_fit(means[0][1], means[-1][1]),
            }
        out["cases"][tag] = entry
        w100 = entry["windows"].get("100") or entry["windows"].get("50") or {}
        print("%-5s frames=%-5d W=%-4s cum/step=%-8s net/step=%-8s ratio=%-6s shift=%s" % (
            tag, len(fr),
            "100" if "100" in entry["windows"] else "50",
            w100.get("cum_per_step"), w100.get("net_per_step"),
            w100.get("ratio_net_over_cum"), w100.get("shift")))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
