#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向 A 闸门（稠密版）：用相位扫描表 N(t,a) 测 g_t 的变差 V_T。

与本地代理版 `a_vt_drift_proxy.py` 的区别
------------------------------------------
* 代理版从在线 trace 的 (t,age) 抽样重建，样本密度低（每窗口每 age 6-13 条）；
* 本脚本直接用相位扫描表，每个 (t,a) 都是实测中位数，密度充足。
在服务器 `/root/autodl-tmp/PBR` 下运行，产出 JSON 拉回本地。

指标定义
--------
读入 N(t,a)（t = 物理步，a = 预条件子年龄），定义

    g_t(a)  = N(t,a) - N(t,0)                     # 以 a=0 归一化，消掉整体抬升
    V_raw(t)   = max_a | N(t+1,a) - N(t,a) |      # 原定义（含整体平移）
    V_shape(t) = max_a | g_{t+1}(a) - g_t(a) |    # 形状变差（本脚本主指标）
    V_T = Σ_t V(t)

再按窗口聚合：把 t 轴切成宽 W 的窗口，每窗口取 V 的均值，得到"每窗口增量"序列，
用于判断 V_T 是收敛到平台（O(1)）还是线性增长（O(T)）。

为什么这两个指标要分开
----------------------
最优周期只依赖 N 在同一 t 下的**形状**，对 N(t,·) → N(t,·)+c 不变。
所以一条整体水涨船高的老化曲线，V_raw 会线性增长而 V_shape ≈ 0。
写进论文的必须是 V_shape；V_raw 只在需要和原始定义对齐时报告。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import CFG, ORDER, load_phase  # noqa: E402

WIDTHS = (25, 50, 100, 200, 400)
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR/vt_dense.json")


def dense(tab):
    """tab: {(t,a): N}, t 从 1 起。返回 (Ts 排序列表, shape N)。"""
    ts = sorted({t for (t, _a) in tab})
    as_ = sorted({a for (_t, a) in tab})
    return ts, as_


def variations(tab, ts, as_, min_a=3):
    """返回逐 t 的 (V_raw, V_shape)；要求该 t 与 t+1 都有足够 age 观测。"""
    raw, shape = [], []
    for t0, t1 in zip(ts, ts[1:]):
        p0 = {a: tab[(t0, a)] for a in as_ if (t0, a) in tab}
        p1 = {a: tab[(t1, a)] for a in as_ if (t1, a) in tab}
        common = sorted(set(p0) & set(p1))
        pos = [a for a in common if a > 0]
        if len(common) < min_a or not pos:
            continue
        raw.append(max(abs(p1[a] - p0[a]) for a in common))
        # 归一化：以两帧共同的最小 age（优先 0）为基准
        b0 = 0 if 0 in common else common[0]
        shape.append(max(abs((p1[a] - p1[b0]) - (p0[a] - p0[b0])) for a in pos))
    return raw, shape


def windowed(v, W):
    """把逐 t 变差按窗口宽 W 取均值，返回每窗口序列。"""
    if not v:
        return []
    out = []
    for i in range(0, len(v), W):
        chunk = v[i:i + W]
        if len(chunk) >= max(3, W // 5):
            out.append(st.mean(chunk))
    return out


def fit_trend(seq):
    """返回 (窗口数为 n 时的累积总量, 尾部斜率/首段均值比)。比值 < 0.5 记为收敛。"""
    if not seq:
        return 0.0, None, None
    cum, s = [], 0.0
    for x in seq:
        s += x
        cum.append(s)
    n = len(cum)
    if n < 4:
        return s, None, None
    k = max(2, n // 3)
    tail = cum[-k:]
    xs = list(range(len(tail)))
    mx, my = st.mean(xs), st.mean(tail)
    den = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, tail)) / den if den else 0.0
    head = st.mean(seq[:k])
    ratio = slope / head if head > 0 else None
    return s, slope, ratio


def main():
    out = {"kind": "VT_dense_from_phase_scan", "P2": P2, "widths": list(WIDTHS),
           "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                              # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "load_phase returned None"}
            continue
        tab = ph["tab"]
        ts, as_ = dense(tab)
        raw, shape = variations(tab, ts, as_)
        entry = {"n_points": len(tab), "n_steps": len(ts),
                 "age_max": (max(as_) if as_ else None),
                 "rho_r1": ph.get("r1"), "s": ph.get("s"),
                 "T": ph.get("T"), "B0": ph.get("B0"),
                 "V_raw_total": round(sum(raw), 2),
                 "V_shape_total": round(sum(shape), 2),
                 "V_shape_per_step": round(sum(shape) / len(shape), 4) if shape else None,
                 "windows": {}}
        for W in WIDTHS:
            seq = windowed(shape, W)
            tot, slope, ratio = fit_trend(seq)
            entry["windows"][str(W)] = {
                "n_windows": len(seq),
                "V_shape_cum": round(tot, 2),
                "per_window": round(tot / len(seq), 3) if seq else None,
                "tail_slope": round(slope, 3) if slope is not None else None,
                "slope_over_head": round(ratio, 3) if ratio is not None else None,
                "converged": (ratio is not None and ratio < 0.5),
            }
        out["cases"][tag] = entry
        w = entry["windows"]
        print("%-5s steps=%-5d ages<=%-1s Vshp_tot=%-9.1f Vshp/step=%-7s  " %
              (tag, entry["n_steps"], entry["age_max"],
               entry["V_shape_total"], entry["V_shape_per_step"]), end="")
        print(" ".join("W%s=%s" % (W, w[str(W)]["per_window"]) for W in WIDTHS))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
