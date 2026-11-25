#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""m=1 之后必须回答的问题：为什么相位方差还是 92.3%？

发现：C4 的 (age, phase) 二分图在三个干净 arm 上都是 **m=1**（16 个相位、
88–121 个年龄全在一个分量里，696–724 条边）。按方向一的判据，$m=1$ 意味着
**可识别**，$m-1=0$ 条激励即可。

但噪声诊断（`noise_diagnosis_20261029.md`）测出 C4 的相位间方差占 95.7%、
相位校正后仍剩 92.3%。两者必须同时解释。三个候选：

  H1  **共线性**：图连通但设计矩阵病态——age 与 phase 在时间上共同演化，
      于是虽可识别、方差极大。可识别 ≠ 估得准。
  H2  **可加性失效**：$\eta(a,j)$ 不是 $f(a)+q(j)$，存在交互项。
      加性模型下"相位校正"必然残留，这不是不可识别，是模型错。
  H3  **估计量实现问题**：代码里 `dN` 只按 age 索引、把相位混在一起
      （`S.dN[S.runAge].push_back(...)`），所以 92.3% 是实现选择的结果，
      不是数据本身不可识别。

判法：对 C4 trace 的 `its` 做两因子方差分解
  · 主效应 age、主效应 phase、交互 age×phase 各占多少
  · H1：除非共线性极高，否则主效应应能吃掉大部分方差
  · H2：若交互项占比大 → 加性失效
  · H3：若主效应+（近似）可加即可解释 95.7%，而代码只用了 age → 实现问题
"""
import collections
import csv
import json
import os
import statistics as st
import sys

BASE = os.environ.get("STEPB", "tmp/stepB/final/full")
ARMS = ("r1_index", "r2_index", "r3_index")
OUT = os.environ.get("OUT", "/tmp/vt_m_why.json")


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"step": int(r["step"]), "age": int(r["age"]),
                             "phase": int(r["phase"] or 0),
                             "its": float(r["its"]),
                             "known": int(r.get("phase_known") or 0)})
            except (KeyError, ValueError):
                continue
    return rows


def two_way(rows):
    """不平衡两因子分解：总平方和 = age主 + phase主 + 交互残差（顺序无关的近似）。"""
    n = len(rows)
    if n < 10:
        return None
    y = [r["its"] for r in rows]
    grand = st.mean(y)
    sst = sum((v - grand) ** 2 for v in y)
    if sst <= 0:
        return None
    ga = collections.defaultdict(list)
    gp = collections.defaultdict(list)
    for r in rows:
        ga[r["age"]].append(r["its"])
        gp[r["phase"]].append(r["its"])
    ma = {k: st.mean(v) for k, v in ga.items()}
    mp = {k: st.mean(v) for k, v in gp.items()}
    ssb_age = sum(len(v) * (ma[k] - grand) ** 2 for k, v in ga.items())
    ssb_phase = sum(len(v) * (mp[k] - grand) ** 2 for k, v in gp.items())
    # 交互残差：观测 - (grand + age效应 + phase效应)
    ss_res = 0.0
    for r in rows:
        pred = grand + (ma[r["age"]] - grand) + (mp[r["phase"]] - grand)
        ss_res += (r["its"] - pred) ** 2
    return {
        "n": n,
        "ss_total": round(sst, 2),
        "pct_age": round(100 * ssb_age / sst, 2),
        "pct_phase": round(100 * ssb_phase / sst, 2),
        "pct_interaction_plus_noise": round(100 * ss_res / sst, 2),
        "n_ages": len(ga), "n_phases": len(gp),
        "age_sd_between": round(st.pstdev(list(ma.values())), 3),
        "phase_sd_between": round(st.pstdev(list(mp.values())), 3),
    }


def collinearity(rows):
    """age 与 phase 的 Pearson 相关，以及"每个年龄见到的相位数"分布。"""
    a = [r["age"] for r in rows]
    p = [r["phase"] for r in rows]
    if len(a) < 3:
        return None
    ma, mp = st.mean(a), st.mean(p)
    num = sum((x - ma) * (y - mp) for x, y in zip(a, p))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mp) ** 2 for y in p)) ** 0.5
    per_age = collections.defaultdict(set)
    for r in rows:
        per_age[r["age"]].add(r["phase"])
    counts = [len(v) for v in per_age.values()]
    return {"pearson_age_phase": round(num / den, 4) if den else None,
            "phases_per_age_min": min(counts), "phases_per_age_median":
            st.median(counts), "phases_per_age_max": max(counts)}


def main():
    out = {}
    for arm in ARMS:
        path = os.path.join(BASE, "C4", arm, "trace.csv")
        if not os.path.exists(path):
            continue
        rows = load(path)
        first_known = min((r["step"] for r in rows if r["known"] == 1), default=None)
        warm = (first_known - 1) if first_known else 0
        post = [r for r in rows if r["step"] > warm]
        age_ge1 = [r for r in post if r["age"] >= 1]

        out[arm] = {
            "n_post": len(post), "n_post_age_ge1": len(age_ge1),
            "two_way_all_post": two_way(post),
            "two_way_age_ge1": two_way(age_ge1),
            "collinearity_all_post": collinearity(post),
        }
        print("=== %s ===" % arm)
        for key in ("two_way_all_post", "two_way_age_ge1"):
            d = out[arm][key]
            if d:
                print("  %-18s n=%-5d age=%-6s phase=%-6s inter+noise=%-6s (ages=%d phases=%d)"
                      % (key, d["n"], d["pct_age"], d["pct_phase"],
                         d["pct_interaction_plus_noise"], d["n_ages"], d["n_phases"]))
        c = out[arm]["collinearity_all_post"]
        print("  collinearity: r(age,phase)=%s  phases/age median=%s min=%s max=%s"
              % (c["pearson_age_phase"], c["phases_per_age_median"],
                 c["phases_per_age_min"], c["phases_per_age_max"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
