#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""弱侧 delta 的来源拆分：局地老化 vs 基线漂移（因果重放）。

判定问题
--------
弱老化 trace 上，判据里的 delta(a)=median(M - median(levels)) 会出现正值。
C1/C4/C5 上预热后有重建依赖它。这些正值是真实的年龄老化，还是
"median(levels) 代表不了当前基线" 造成的漂移泄漏？

做法
----
按生产 pbr_policy.h 的因果顺序重放固定 trace，一次只换 delta 的样本来
源，其余（lvl、avg、是否重建、levels 更新）全部不动：

  prod     : dN[a] <- M - median(levels)          （生产口径，含漂移）
  local    : dN[a] <- M - lvl                     （去掉漂移项）
  phlocal  : 同 local，但 dN 键为 (phase, a)      （相位内局地）

三种口径下重建**已知**（trace 固定），只重新归因每次重建的触发者：
  lvl      : lvl > avg
  delta    : lvl <= avg 但 lvl + max(0,delta) > avg
  neither  : 两者都不成立（说明 delta 估计没跟上，或有别的东西在推动）

审计边界
--------
不改生产代码、不跑求解器；固定 trace 上的归因。
lvl 用 M = its - q（pbr_policy.h:255-256）。决策年龄用 step - heldBase
（重建行的 age 列是决策后状态，恒为 0）。
"""
import csv, json, os, statistics as st

CASES = ["Blankenbach", "C1", "C3", "C4", "C5", "MOOSE"]
ROOT = os.environ.get("PBR_ROOT", ".")
OUT = os.environ.get("OUT", "weak_delta_decomp.json")


def load(case, sub="r1_index"):
    p = os.path.join(ROOT, "tmp/stepB/final/full", case, sub, "trace.csv")
    if not os.path.exists(p):
        return None
    rows = []
    for r in csv.DictReader(open(p)):
        rows.append(dict(step=int(r["step"]), heldBase=int(r["heldBase"]),
                         age=int(r["age"]), its=float(r["its"]),
                         q=float(r["q"] or 0.0), est=float(r["est"] or 0.0),
                         avg=float(r["avg"] or 0.0), phase=r["phase"],
                         reb=r["rebuild"].strip() == "1",
                         warm=r["est_dsrc"].strip() == "warmup"))
    for r in rows:
        r["M"] = r["its"] - r["q"]
    return rows


def estimate(dN, age, phase, mode):
    """复刻生产估计器：hit -> 中位；否则按最大两个年龄割线外推；再退 flat/0。"""
    def key(a):
        return (phase, a) if mode == "phlocal" else a

    def age_of(k):
        return k[1] if isinstance(k, tuple) else k

    k0 = key(age)
    if k0 in dN and dN[k0]:
        return st.median(dN[k0]), "hit"
    ks = sorted((k for k in dN if dN[k]), key=age_of)
    if len(ks) >= 2:
        a2, a1 = age_of(ks[-1]), age_of(ks[-2])
        d2, d1 = st.median(dN[ks[-1]]), st.median(dN[ks[-2]])
        return d2 + (d2 - d1) / max(1e-9, a2 - a1) * (age - a2), "extrap"
    if ks:
        return st.median(dN[ks[-1]]), "flat"
    return 0.0, "boot"


def replay(case, mode, sub="r1_index"):
    rows = load(case, sub)
    if rows is None:
        return {"error": "missing"}
    levels, dN = [], {}
    last = None
    stats = dict(decisions=0, rebuilds_post=0, lvl_alone=0, delta_dec=0, neither=0)
    detail = []
    age_rows = {}          # age -> [(resid, local, drift)]
    for r in rows:
        if r["warm"]:
            if r["reb"]:
                levels.append(r["M"]); last = r["M"]
            continue
        if not levels:
            continue
        stats["decisions"] += 1
        base = st.median(levels)
        a = r["step"] - r["heldBase"]        # 决策时真实年龄
        if r["reb"]:
            stats["rebuilds_post"] += 1
            d, src = estimate(dN, a, r["phase"], mode)
            dmax = max(0.0, d)
            lvl, avg = last, r["avg"]
            if lvl > avg:
                stats["lvl_alone"] += 1; cls = "lvl"
            elif lvl + dmax > avg:
                stats["delta_dec"] += 1; cls = "delta"
            else:
                stats["neither"] += 1; cls = "neither"
            detail.append(dict(step=r["step"], age=a, phase=r["phase"],
                               lvl=round(lvl, 1), avg=round(avg, 2),
                               delta_hat=round(d, 2), src=src,
                               delta_applied=round(r["est"] - lvl, 2),
                               gap=round(avg - lvl, 2), cls=cls))
            levels.append(r["M"]); last = r["M"]
        else:
            if mode == "prod":
                dN.setdefault(a, []).append(r["M"] - base)
                rec = (r["M"] - base, r["M"] - last, last - base)
            elif mode == "local":
                dN.setdefault(a, []).append(r["M"] - last)
                rec = (r["M"] - base, r["M"] - last, last - base)
            else:
                dN.setdefault((r["phase"], a), []).append(r["M"] - last)
                rec = (r["M"] - base, r["M"] - last, last - base)
            age_rows.setdefault(a, []).append(rec)

    # delta 的量级：按年龄看三种成分的中位
    breakdown = {}
    for a in sorted(age_rows):
        g = age_rows[a]
        breakdown[a] = dict(
            n=len(g),
            resid=round(st.median([x[0] for x in g]), 2),
            local=round(st.median([x[1] for x in g]), 2),
            drift=round(st.median([x[2] for x in g]), 2))
    stats["breakdown"] = breakdown
    stats["detail"] = detail
    stats["case"] = case
    stats["mode"] = mode
    return stats


def main():
    out = {"kind": "weak_delta_decomposition_causal", "cases": {}}
    agg = {}
    for c in CASES:
        out["cases"][c] = {}
        for mode in ("prod", "local", "phlocal"):
            r = replay(c, mode)
            out["cases"][c][mode] = r
            if "error" in r:
                continue
            t = agg.setdefault(mode, dict(reb=0, lvl=0, delta=0, neither=0))
            t["reb"] += r["rebuilds_post"]
            t["lvl"] += r["lvl_alone"]
            t["delta"] += r["delta_dec"]
            t["neither"] += r["neither"]
    out["aggregate"] = agg
    json.dump(out, open(OUT, "w"), indent=1)

    print("%-13s %-7s %5s %5s %5s %5s" % ("case", "mode", "reb", "lvl", "delta", "neith"))
    for c in CASES:
        for mode in ("prod", "local", "phlocal"):
            r = out["cases"][c][mode]
            if "error" in r:
                print("%-13s %-7s ERROR" % (c, mode)); continue
            print("%-13s %-7s %5d %5d %5d %5d" % (c, mode, r["rebuilds_post"],
                  r["lvl_alone"], r["delta_dec"], r["neither"]))
    print()
    for mode, t in agg.items():
        print("TOTAL %-7s reb=%d lvl=%d delta=%d neither=%d"
              % (mode, t["reb"], t["lvl"], t["delta"], t["neither"]))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
