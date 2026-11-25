#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向 A 闸门：g_t 变差 V_T 的实测代理。

用途
----
判定第二篇方向 A 的闸门：老化曲线 *形状* 的变差随时间窗是收敛（O(1)）还是线性增长（O(T)）。

数据来源与代理的正当性
----------------------
本脚本**不用**稠密相位表 N(t,a)（那批 phs_* 文件在服务器，本地没有），而是从
`tmp/stepB/final/full/<case>/r{1,2,3}_{index,old}/trace.csv` 重建：
每行给出该物理步的 (step, age, its, phase)，即策略实际走到的一个 (t,a) 观测点。

对固定窗口宽 W：
    g_w(a) = median{ its : step in [wW,(w+1)W), age == a }
    gt_w(a) = g_w(a) - g_w(0)          # 以 age=0 归一化，消掉整体抬升（与 mu(t) 同理）
    V_raw(w)   = max_a | g_w(a) - g_{w-1}(a) |                # 原定义
    V_shape(w) = max_a | gt_w(a) - gt_{w-1}(a) |              # 形状变差（本脚本主指标）
    V_T = cumsum_w V(w)

判读
----
对每个 (case, arm, W) 报告 V_T 与窗口数 nw 的比值，并对后 2/3 窗口做线性拟合：
    * 斜率随 nw 趋于 0、V_T 收敛到平台  → O(1)（情形一，理论文章可写）
    * V_T ≈ c * nw，斜率不衰减          → O(T)（情形二，须改用漂移容忍证书）

**这是代理，不是相位表**：不同 age 在不同 t 被观测，样本量随 age 衰减。
结论应按"多个 W 是否一致"来看，不看单个 W 的值。
"""
import csv
import glob
import json
import os
import statistics as st
import sys

ROOT = os.environ.get("PBR_ROOT", ".")
TRACE_GLOB = os.path.join(ROOT, "tmp/stepB/final/full/*/*/trace.csv")
WIDTHS = (50, 100, 200)
MIN_CELL = 3          # 一个 (window, age) 单元格至少几行才参与
MAX_AGE = 20          # 超过此 age 的观测样本太稀疏，截断


def load(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((int(r["step"]), int(r["age"]), int(r["its"])))
            except (ValueError, KeyError):
                continue
    return rows


def cross_sections(rows, W):
    """返回 [(w, {age: median_its}), ...]，只保留年龄 0 存在且样本够的窗口。"""
    cells = {}
    for t, a, its in rows:
        if a > MAX_AGE:
            continue
        cells.setdefault((t // W, a), []).append(its)
    wins = sorted({w for (w, _a) in cells})
    out = []
    for w in wins:
        prof = {a: st.median(v) for (ww, a), v in cells.items()
                if ww == w and len(v) >= MIN_CELL}
        if 0 in prof and len(prof) >= 2:
            out.append((w, prof))
    return out


def variations(sections):
    """返回 (V_raw 序列, V_shape 序列)，长度 = len(sections)-1。"""
    raw, shape = [], []
    for (w0, p0), (w1, p1) in zip(sections, sections[1:]):
        common = sorted(set(p0) & set(p1) - {0})
        if not common:
            continue
        raw.append(max(abs(p1[a] - p0[a]) for a in common))
        shape.append(max(abs((p1[a] - p1[0]) - (p0[a] - p0[0])) for a in common))
    return raw, shape


def grow(v):
    """V_T 的收敛性：返回 (V_T, 后 2/3 斜率, 有效窗口数, 是否收敛)。"""
    if not v:
        return 0.0, 0.0, 0, None
    n = len(v)
    cum = []
    s = 0.0
    for x in v:
        s += x
        cum.append(s)
    k = max(2, (2 * n) // 3)
    tail = cum[n - k:]
    if len(tail) >= 2:
        xs = list(range(len(tail)))
        mx, my = st.mean(xs), st.mean(tail)
        den = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, tail)) / den if den else 0.0
    else:
        slope = float("nan")
    # 收敛判据：尾部斜率 < 首段平均增量的一半，且最后 1/3 的增量总和 < 前 1/3 的一半
    head_total = st.mean(v[: max(1, n // 3)]) if v else 0.0
    conv = None
    if n >= 6 and head_total > 0:
        conv = (slope < 0.5 * head_total)
    return s, slope, n, conv


def main():
    files = sorted(glob.glob(TRACE_GLOB))
    if not files:
        print("no trace under %s" % TRACE_GLOB, file=sys.stderr)
        return 2
    cases = {}
    for path in files:
        parts = path.replace("\\", "/").split("/")
        case, arm = parts[-3], parts[-2]
        rows = load(path)
        if len(rows) < 20:
            continue
        entry = {"n_rows": len(rows),
                 "steps": max(t for t, _a, _i in rows) - min(t for t, _a, _i in rows) + 1,
                 "widths": {}}
        for W in WIDTHS:
            sec = cross_sections(rows, W)
            raw, shape = variations(sec)
            vr = grow(raw)
            vs = grow(shape)
            entry["widths"][str(W)] = {
                "n_sections": len(sec),
                "V_raw_total": round(vr[0], 3),
                "V_raw_per_window": round(vr[0] / vr[2], 4) if vr[2] else None,
                "V_shape_total": round(vs[0], 3),
                "V_shape_per_window": round(vs[0] / vs[2], 4) if vs[2] else None,
                "V_shape_tail_slope": round(vs[1], 4) if vs[1] is not None else None,
                "V_shape_converged": vs[3],
                "V_shape_series": [round(x, 2) for x in shape],
            }
        cases.setdefault(case, {})[arm] = entry

    out = {"kind": "VT_proxy_from_online_trace",
           "note": "proxy: windowed medians of observed (t,age); NOT the dense phase table",
           "widths": list(WIDTHS), "min_cell": MIN_CELL, "max_age": MAX_AGE,
           "cases": cases}
    dst = os.path.join(ROOT, "docs/theory_checks/vt_proxy_20261031.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("%-12s %-9s %4s %6s %10s %10s %9s %s" %
          ("case", "arm", "W", "sect", "Vshp/wnd", "Vs_ser0", "tail", "conv"))
    for case in sorted(cases):
        for arm in sorted(cases[case]):
            e = cases[case][arm]
            for W in WIDTHS:
                w = e["widths"][str(W)]
                print("%-12s %-9s %4d %6d %10s %10s %9s %s" % (
                    case, arm, W, w["n_sections"],
                    w["V_shape_per_window"],
                    w["V_shape_series"][:3],
                    w["V_shape_tail_slope"], w["V_shape_converged"]))
    print("\nwrote %s" % dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
