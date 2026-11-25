#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查相位/锚点混叠：拼出来的 (t,a) 表里有多少是"缝合伪迹"。

背景
----
相位扫描由 7 个锚点文件组成（fx 为 B94..B100）。每个文件在自己的锚点 B 上冻结、
此后**每 7 步**再冻结一次，因此文件 B 只覆盖满足
    t - a ≡ B  (mod 7)
的单元格。7 个 B 连续，恰好在同余类上互补：**每个 (t,a) 只由唯一一个文件提供**。
所以 `load_phase` 里对同一格的 median 其实是对**单个**样本取中位数，等于没平均，
我此前文档里写的"7 个锚点取中位数已把相位平均掉"是错的。

由此产生的风险：同一张横截面 {N(t,a): a=0..6} 里，不同 age 来自**不同的锚点文件**，
而不同锚点的冻结位置相对步内相位序列错开。若这个错开在横截面上留下系统性锯齿，
那么按 t 相邻差分算出的 eta / V_shape 里就混有 7 周期伪迹。

本脚本测三件事
--------------
1. 单元格样本数分布（验证"每格 1 个样本"）。
2. 7 周期分量强度：按 t mod 7 分组，算组内均值剖面，看组间差异有多大。
3. eta 与 V_shape 扣除 7 周期分量后的残值 —— 残值才是物理部分。
"""
import collections
import json
import os
import re
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import CFG, ORDER, phase_scan_anchor, _rows, _per_step_N  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_alias.json")
A = 6
K = 7
KMAX = 20


def build_with_provenance(tag):
    """返回 (tab, prov)：tab[(t,a)] = 样本列表，prov[(t,a)] = 来源锚点集合。"""
    lvl, T, B0 = CFG[tag]
    Bscan = phase_scan_anchor(tag)
    cells = collections.defaultdict(list)
    prov = collections.defaultdict(set)
    for B in range(Bscan - A, Bscan + 1):
        c = os.path.join(P2, "phs_%s_B%d_K%d_r1.csv" % (tag, B, K))
        l = os.path.join(P2, "phs_%s" % tag, "log.B%dK%d_r1" % (B, K))
        if not (os.path.exists(c) and os.path.exists(l)):
            continue
        try:
            rr = _rows(c)
            seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            Ns = _per_step_N(l)
            n = min(len(steps), len(Ns))
            for i in range(n):
                x = steps[i]
                rf = int(x["reusedFrom"])
                age = 0 if rf < 0 else i + 1 - rf
                cells[(i + 1, age)].append(Ns[i])
                prov[(i + 1, age)].add(B)
        except Exception:                              # noqa: BLE001
            pass
    return cells, prov


def main():
    out = {"kind": "alias_check", "P2": P2, "cases": {}}
    for tag in ORDER:
        cells, prov = build_with_provenance(tag)
        if not cells:
            out["cases"][tag] = {"error": "no cells"}
            continue
        counts = collections.Counter(len(v) for v in cells.values())
        multisrc = sum(1 for v in prov.values() if len(v) > 1)

        tab = {k: st.median(v) for k, v in cells.items()}
        ts = sorted({t for (t, _a) in tab})
        as_ = sorted({a for (_t, a) in tab})

        # 横截面 g_t(a) = N(t,a) - N(t,0)
        prof = {}
        for t in ts:
            p = {a: tab[(t, a)] for a in as_ if (t, a) in tab}
            if 0 in p and len(p) >= 4:
                prof[t] = {a: p[a] - p[0] for a in p if a > 0}
        if len(prof) < 14:
            out["cases"][tag] = {"error": "too few frames", "n": len(prof)}
            continue

        # 7 周期分量：按 t mod 7 分组取均值
        groups = collections.defaultdict(list)
        for t, g in prof.items():
            groups[t % 7].append(g)
        group_mean = {}
        for r, gs in groups.items():
            common = set(gs[0])
            for g in gs[1:]:
                common &= set(g)
            common = sorted(common)
            if common:
                group_mean[r] = {a: st.mean(g[a] for g in gs) for a in common}

        # 组间差异（7 周期伪迹幅度）
        allc = None
        for m in group_mean.values():
            allc = set(m) if allc is None else (allc & set(m))
        allc = sorted(allc or [])
        between = 0.0
        if len(allc) >= 2 and len(group_mean) >= 2:
            between = max(
                max(m[a] for m in group_mean.values()) - min(m[a] for m in group_mean.values())
                for a in allc)

        # eta 与 V_shape：原始 vs 扣除 7 周期分量
        ts2 = sorted(prof)
        eta_raw, eta_res, vs_raw, vs_res = [], [], [], []
        for t0, t1 in zip(ts2, ts2[1:]):
            g0, g1 = prof[t0], prof[t1]
            common = sorted(set(g0) & set(g1))
            if not common:
                continue
            vs_raw.append(max(abs(g1[a] - g0[a]) for a in common))
            r0 = t0 % 7
            r1 = t1 % 7
            if r0 in group_mean and r1 in group_mean:
                m0, m1 = group_mean[r0], group_mean[r1]
                cc = [a for a in common if a in m0 and a in m1]
                if cc:
                    vs_res.append(max(abs((g1[a] - m1[a]) - (g0[a] - m0[a])) for a in cc))
            # c 向量口径的 eta
            p0 = {a: g0[a] for a in g0}
            p1 = {a: g1[a] for a in g1}

            def cvec(g):
                full = dict(g)
                full[0] = 0.0
                v = {}
                for Kk in range(1, KMAX + 1):
                    aa = [a for a in range(Kk) if a in full]
                    if len(aa) < Kk:
                        break
                    v[Kk] = st.mean(full[a] for a in aa)
                return v
            v0, v1 = cvec(p0), cvec(p1)
            cc = sorted(set(v0) & set(v1))
            if len(cc) >= 2:
                d = {Kk: v1[Kk] - v0[Kk] for Kk in cc}
                dbar = st.mean(d.values())
                eta_raw.append(max(abs(d[Kk] - dbar) for Kk in cc))
                if r0 in group_mean and r1 in group_mean:
                    def cvec_m(m):
                        full = dict(m)
                        full[0] = 0.0
                        v = {}
                        for Kk in range(1, KMAX + 1):
                            aa = [a for a in range(Kk) if a in full]
                            if len(aa) < Kk:
                                break
                            v[Kk] = st.mean(full[a] for a in aa)
                        return v
                    w0, w1 = cvec_m(m0), cvec_m(m1)
                    cc2 = sorted(set(w0) & set(w1))
                    if len(cc2) >= 2:
                        d0 = {Kk: v0[Kk] - w0[Kk] for Kk in cc2 if Kk in v0}
                        d1 = {Kk: v1[Kk] - w1[Kk] for Kk in cc2 if Kk in v1}
                        kk = sorted(set(d0) & set(d1))
                        if len(kk) >= 2:
                            dd = {Kk: d1[Kk] - d0[Kk] for Kk in kk}
                            db = st.mean(dd.values())
                            eta_res.append(max(abs(dd[Kk] - db) for Kk in kk))

        e = {"n_cells": len(cells), "n_frames": len(prof),
             "cell_sample_counts": dict(counts),
             "cells_with_multi_source": multisrc,
             "period7_between_amplitude": round(between, 2),
             "vs_raw_mean": round(st.mean(vs_raw), 3) if vs_raw else None,
             "vs_res_mean": round(st.mean(vs_res), 3) if vs_res else None,
             "vs_frac_removed": (round(1 - st.mean(vs_res) / st.mean(vs_raw), 3)
                                 if vs_raw and vs_res and st.mean(vs_raw) else None),
             "eta_raw_mean": round(st.mean(eta_raw), 3) if eta_raw else None,
             "eta_res_mean": round(st.mean(eta_res), 3) if eta_res else None,
             "eta_frac_removed": (round(1 - st.mean(eta_res) / st.mean(eta_raw), 3)
                                  if eta_raw and eta_res and st.mean(eta_raw) else None)}
        out["cases"][tag] = e
        print("%-5s cells=%-5d 样本数分布=%s 多源格=%d | 7周期幅度=%-6s "
              "Vshp %s→%s(-%.0f%%) eta %s→%s(-%.0f%%)" % (
                  tag, e["n_cells"], e["cell_sample_counts"], multisrc,
                  e["period7_between_amplitude"],
                  e["vs_raw_mean"], e["vs_res_mean"], 100 * (e["vs_frac_removed"] or 0),
                  e["eta_raw_mean"], e["eta_res_mean"], 100 * (e["eta_frac_removed"] or 0)))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
