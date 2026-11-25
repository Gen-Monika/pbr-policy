#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方向 A 闸门（分解版）：把 g_t 的变差拆成「低频谱漂移」与「高频涨落」。

为什么必须拆
------------
稠密版 `a_vt_dense.py` 逐 t 相邻差分测得的 V_shape/步 在七个配置上几乎是常数
（fx 16.5、sth 6.3、x3 23.5），按定义就是 V_T = Θ(T)。但这**不能直接判成"漂移"**：
N(t,a) 是"物理步 t、年龄 a 时的迭代数"，相邻两步之间曲线会变，既可能是因为老化规律
本身在移动（要研究的漂移），也可能只是因为 t 处的物理状态在照常演化（这本来就是要重建
的原因，不是新现象）。

分解
----
对窗口宽 W，令 m_w(a) = mean_{t in window w} g_t(a)（g_t(a)=N(t,a)-N(t,0)）：

    D_W  = Σ_w max_a | m_{w+1}(a) - m_w(a) |      # 低频谱：窗口均值怎么移动 → 漂移预算
    F_W  = Σ_w mean_{t in w} max_a | g_t(a) - m_w(a) |   # 高频：窗口内涨落

判读
----
* 若 D_W 随 W 增大而**显著下降**并趋于平台 → 低频分量有界，V_T=Θ(T) 由涨落造成，
  真正的漂移预算 ε 应按 D_W/W 估计，而不是 V_shape/步；
* 若 D_W 不随 W 下降 → 各时间尺度上都在漂移，是真正的非平稳，证书的 H∝1/ε 才成立。

同时报告 K*(t)：给定 t 的横截面，按 c(K)=mean_{a<K} N(t,a) + ρ/K 求最优周期，
统计它在时间上改变多少次、改变量多大。这是"标定多久失效"最直接的读数。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import CFG, ORDER, load_phase  # noqa: E402

WIDTHS = (20, 50, 100, 200, 400, 800)
OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_decomp.json")


def build(tab, ts, as_):
    """返回 {t: {a: N}}，只保留有 a=0 的帧（归一化基准）。"""
    frames = {}
    for t in ts:
        prof = {a: tab[(t, a)] for a in as_ if (t, a) in tab}
        if 0 in prof and len(prof) >= 4:
            frames[t] = prof
    return frames


def gvec(prof, ages):
    """以 a=0 归一化后的形状向量。"""
    return {a: prof[a] - prof[0] for a in ages if a in prof}


def decompose(frames, W):
    ts = sorted(frames)
    ages = sorted({a for p in frames.values() for a in p if a > 0})
    wins, cur = [], []
    for t in ts:
        cur.append(t)
        if len(cur) == W:
            wins.append(cur)
            cur = []
    if len(cur) >= max(5, W // 4):
        wins.append(cur)
    if len(wins) < 2:
        return None
    means, fluct = [], []
    for w in wins:
        gs = [gvec(frames[t], ages) for t in w]
        common = set(gs[0])
        for g in gs[1:]:
            common &= set(g)
        common = sorted(common)
        if not common:
            means.append(None)
            fluct.append(0.0)
            continue
        m = {a: st.mean(g[a] for g in gs) for a in common}
        means.append(m)
        fluct.append(st.mean(
            max(abs(g[a] - m[a]) for a in common) for g in gs))
    drift = 0.0
    for m0, m1 in zip(means, means[1:]):
        if not m0 or not m1:
            continue
        common = sorted(set(m0) & set(m1))
        if common:
            drift += max(abs(m1[a] - m0[a]) for a in common)
    return {"n_windows": len(wins),
            "D_drift": round(drift, 2),
            "D_per_window": round(drift / max(1, len(wins) - 1), 3),
            "F_fluct_per_window": round(st.mean([f for f in fluct if f]), 3) if any(fluct) else None,
            "window_steps": [len(w) for w in wins][:6]}


def kstar_track(frames, rho, kmax=20):
    """逐 t 求最优固定周期 K*(t)，返回序列与变更统计。"""
    ts = sorted(frames)
    track = []
    for t in ts:
        prof = frames[t]
        best, bk = None, None
        for K in range(1, kmax + 1):
            ages = [a for a in range(K) if a in prof]
            if len(ages) < K:
                break
            c = st.mean(prof[a] for a in ages) + rho / K
            if best is None or c < best:
                best, bk = c, K
        if bk:
            track.append(bk)
    if not track:
        return None
    ch = [abs(b - a) for a, b in zip(track, track[1:])]
    big = sum(1 for x in ch if x >= 2)
    return {"n": len(track), "min": min(track), "max": max(track),
            "median": st.median(track),
            "n_changes": sum(1 for x in ch if x > 0),
            "n_big_changes": big,
            "record": track[:40]}


def main():
    out = {"kind": "VT_decomposition", "P2": P2, "widths": list(WIDTHS), "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                          # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        tab = ph["tab"]
        ts = sorted({t for (t, _a) in tab})
        as_ = sorted({a for (_t, a) in tab})
        frames = build(tab, ts, as_)
        entry = {"n_frames": len(frames), "rho_r1": ph.get("r1"),
                 "T": ph.get("T"), "B0": ph.get("B0"),
                 "kstar": kstar_track(frames, ph.get("r1") or 10.0),
                 "decomp": {}}
        for W in WIDTHS:
            d = decompose(frames, W)
            if d:
                entry["decomp"][str(W)] = d
        out["cases"][tag] = entry
        print("%-5s frames=%-5d K*=%s" % (
            tag, entry["n_frames"],
            (entry["kstar"] or {}).get("min")), end="  ")
        print(" ".join("W%s D=%.0f F=%.1f" % (
            W, entry["decomp"][str(W)]["D_drift"], entry["decomp"][str(W)]["F_fluct_per_window"])
            for W in WIDTHS if str(W) in entry["decomp"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
