#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 C4 的相位级 trace 上数 m：年龄–相位二分图的连通分量数。

定义（照方向文档）
------------------
$G\subseteq\mathbb{Z}_{\ge0}\times\{0..s-1\}$，边 $(a,j)$ 存在 ⟺ 该算例在某一时刻
以相位 $j$ 观测到年龄 $a$ 的迭代数。可识别当且仅当 $G$ 连通；有 $m$ 个连通分量
则有 $m$ 维不可识别族（各分量可独立平移），需 $m-1$ 条激励才能恢复可识别性。

数据
----
`tmp/stepB/final/full/C4/<arm>/trace.csv`，`phase` = SNES 迭代数（步内决策单元下标），
`age` = 预条件子年龄，`its` = 该步迭代数。

三种 m 都要报，避免用口径掩盖结论
-------------------------------
1. **$m_{all}$**：用全部行（含预热期 age=0）。
2. **$m_{post}$**：只用 $t>$ 预热结束的行（`phase_known=1` 之后），这是策略真正
   用到的观测。
3. **$m_{age\ge1}$**：排除 age=0（重建步），只看老化观测——phaseLevels 累积的正是这类。

必须注意两个使 m 变小（甚至恒为 1）的机制，要单列：
* age=0 的行把该相位与"重建"连起来，但 age=0 出现在**大量**相位上，会把很多相位
  系到同一个分量上；
* 同一步只有一行，所以同一个 step 不会同时提供两个相位——这不阻碍连通，但决定了
  观测密度。
"""
import collections
import csv
import os
import sys

BASE = os.environ.get(
    "STEPB", "tmp/stepB/final/full")
ARMS = ("r1_index", "r2_index", "r3_index", "r1_old")
OUT = os.environ.get("OUT", "/tmp/vt_m_count.json")


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"step": int(r["step"]), "age": int(r["age"]),
                             "phase": int(r.get("phase") or 0),
                             "its": float(r["its"]),
                             "rebuild": int(r["rebuild"]),
                             "known": int(r.get("phase_known") or 0),
                             "q": float(r.get("q") or 0)})
            except (KeyError, ValueError):
                continue
    return rows


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb

    def ncomp(self):
        return len({self.find(x) for x in self.p})


def components(rows, ages_filter, phase_filter=None):
    uf = UF()
    edges = set()
    for r in rows:
        a, j = r["age"], r["phase"]
        if not ages_filter(a):
            continue
        if phase_filter and not phase_filter(j):
            continue
        uf.find(("a", a))
        uf.find(("j", j))
        uf.union(("a", a), ("j", j))
        edges.add((a, j))
    if not uf.p:
        return None, 0
    # 统计每个分量里各有多少 age 与 phase 节点
    comps = collections.defaultdict(lambda: {"ages": set(), "phases": set()})
    for x in uf.p:
        kind, val = x
        root = uf.find(x)
        comps[root]["ages" if kind == "a" else "phases"].add(val)
    detail = [{"n_ages": len(c["ages"]), "n_phases": len(c["phases"]),
               "ages": sorted(c["ages"])[:12],
               "phases": sorted(c["phases"])}
              for c in comps.values()]
    detail.sort(key=lambda d: (-d["n_ages"], -d["n_phases"]))
    return {"m": len(comps), "n_edges": len(edges), "components": detail}, len(edges)


def main():
    out = {}
    for arm in ARMS:
        path = os.path.join(BASE, "C4", arm, "trace.csv")
        if not os.path.exists(path):
            out[arm] = {"error": "missing"}
            continue
        rows = load(path)
        if not rows:
            out[arm] = {"error": "empty"}
            continue
        # 预热结束 = phase_known 首次为 1 的那一步之前（不是"最后一个 known=0"，
        # 因为后期重建步的 known 也会回落为 0，那样会把几乎全部数据划进预热）
        first_known = min((r["step"] for r in rows if r["known"] == 1), default=None)
        t_warm_end = (first_known - 1) if first_known is not None else 0
        post = [r for r in rows if r["step"] > t_warm_end]
        entry = {
            "n_rows": len(rows),
            "t_warm_end": t_warm_end,
            "n_phases_seen": len({r["phase"] for r in rows}),
            "phase_min": min(r["phase"] for r in rows),
            "phase_max": max(r["phase"] for r in rows),
            "age_max": max(r["age"] for r in rows),
        }
        for name, sel, flt in (
            ("all", lambda a: True, None),
            ("post", lambda a: True, None),
            ("age_ge1", lambda a: a >= 1, None),
            ("post_age_ge1", lambda a: a >= 1, None),
        ):
            rr = post if name.startswith("post") else rows
            res, ne = components(rr, sel, flt)
            entry[name] = res
        out[arm] = entry
        print("=== %s ===" % arm)
        print("  rows=%d warm_end=%d phases=%d..%d (n=%d) age_max=%d"
              % (len(rows), t_warm_end, entry["phase_min"], entry["phase_max"],
                 entry["n_phases_seen"], entry["age_max"]))
        for k in ("all", "post", "age_ge1", "post_age_ge1"):
            r = entry[k]
            if r:
                print("  %-14s m=%-3d edges=%-4d  largest comp: ages=%d phases=%d"
                      % (k, r["m"], r["n_edges"],
                         r["components"][0]["n_ages"], r["components"][0]["n_phases"]))
                if r["m"] > 1:
                    for c in r["components"][1:6]:
                        print("      extra comp: ages=%d phases=%d %s"
                              % (c["n_ages"], c["n_phases"], c["phases"]))
    import json
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
