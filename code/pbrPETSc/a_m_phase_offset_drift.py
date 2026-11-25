#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R-02 的离线裁决：92.3% 到底来自哪，按 (a,j) 分箱 dN 能不能消掉它。

背景
----
`docs/paper2_m_identifiability_20261031.md` §三 断言：C4 相位校正后仍剩 92.3%
的相位方差，原因是 `pbr_policy.h` 的 `S.dN[S.runAge].push_back(...)` 只按年龄索引；
推论是"若把 dN 按 (a,j) 分箱后再估计，92.3% 应显著下降"。

本脚本在**已有的 C4 三臂 trace** 上离线检验这个推论，不跑求解器、不改代码。
四个问题：

  Q1  `dN` 进的是预测器 `est`，还是观测量 `its`？
      → 若 92.3% 是 `its` 的两因子分解，则改 `dN` 在数学上碰不到它。
  Q2  把 `dN` 的键换成 (a,j)，预测误差与决策各变多少？（离线重放，非实跑）
  Q3  若 92.3% 不来自 `dN`，那它来自哪？→ 追查 `model_its = its - q_j` 里的 `q_j`。
  Q4  `q_j` 的误差是"估得不够准"还是"它本身就是时变的"？
      → 若时变，则"在线更新 q_j"这条补救也无效，必须换模型。

口径
----
* 预热结束 = `phase_known` 首次为 1 的那一行（与 `a_m_phase_graph.py` 一致）。
* `its` 是原始 Krylov 迭代数；`model_its = its - q` 是相位校正后的值。
* 冻结的 `q_j` 取 `step > 100` 且 `phase_known==1` 的首个值——**step 99 那行
  offsets 尚未冻结，`q` 列记为 0**，早先版本因此把 phase 1 的 q 误读成 0。
* 两因子分解是不平衡设计的近似，三项之和可超过 100%；只比较相对量级。
* 调和平均取上中位 `v[n//2]`，与 `medianOf()` 一致。

用法
----
    OUT=docs/theory_checks/vt_m_offset_20261101.json \
      python3 -I code/pbrPETSc/a_m_phase_offset_drift.py
"""
import collections
import csv
import json
import os
import statistics as st

BASE = os.environ.get("STEPB", "tmp/stepB/final/full")
OUT = os.environ.get("OUT", "/tmp/vt_m_offset.json")
CASES = ("C1", "C3", "C4", "C5")
ARMS = ("r1_index", "r2_index", "r3_index")
WARM_END = 100


def umed(v):
    """上中位，与 pbr_policy.h 的 medianOf 相同（v[n], n=size/2）。"""
    if not v:
        return 0.0
    s = sorted(v)
    return s[len(s) // 2]


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "step": int(r["step"]), "rebuild": int(r["rebuild"]),
                    "age": int(r["age"]), "its": float(r["its"]),
                    "est": float(r["est"]), "avg": float(r["avg"]),
                    "model": float(r["model_its"]), "phase": int(r["phase"]),
                    "known": int(r["phase_known"]),
                    "q": float(r.get("q") or 0.0), "src": r.get("est_dsrc", ""),
                })
            except (KeyError, ValueError):
                continue
    return rows


def split(rows):
    """返回 (预热结束行号, post 段 age>=1 的行)。"""
    wk = next((i for i, r in enumerate(rows) if r["known"] == 1), None)
    if wk is None:
        return None, []
    return wk, [r for r in rows[wk - 1:] if r["age"] >= 1]


def frozen_q(rows, wk):
    """冻结后的 q_j。跳过 step 99：那一行 offsets 还没冻结，日志里是 0。"""
    q = {}
    for r in rows[wk - 1:]:
        if r["known"] == 1 and r["step"] > WARM_END:
            q.setdefault(r["phase"], round(r["q"], 3))
    return q


def two_way(rows, key):
    """不平衡两因子分解：age 主效应 / phase 主效应 / 交互+残差。"""
    y = [r[key] for r in rows]
    n = len(y)
    if n < 10:
        return None
    grand = sum(y) / n
    sst = sum((v - grand) ** 2 for v in y)
    if sst <= 0:
        return None
    ga, gp = collections.defaultdict(list), collections.defaultdict(list)
    for r in rows:
        ga[r["age"]].append(r[key])
        gp[r["phase"]].append(r[key])
    ma = {k: sum(v) / len(v) for k, v in ga.items()}
    mp = {k: sum(v) / len(v) for k, v in gp.items()}
    sa = sum(len(v) * (ma[k] - grand) ** 2 for k, v in ga.items())
    sp = sum(len(v) * (mp[k] - grand) ** 2 for k, v in gp.items())
    sr = sum((r[key] - (grand + (ma[r["age"]] - grand) + (mp[r["phase"]] - grand))) ** 2
             for r in rows)
    return {"n": n, "pct_age": round(100 * sa / sst, 1),
            "pct_phase": round(100 * sp / sst, 1),
            "pct_resid": round(100 * sr / sst, 1),
            "n_ages": len(ga), "n_phases": len(gp)}


# ---------------------------------------------------------------- Q2: 重放
def replay(rows, mode):
    """按代码的实际顺序重放 decide()，返回每行的预测。

    mode='old'   现行实现：dN 只按年龄索引（键写作 (a,-1)）
    mode='ajan'  反事实：dN 按 (a,j) 索引，不做回落

    三个易错点（初版全错，保真度只有 28.6%）：
      1. `freezePhaseOffsets()` 在 `decide()` 开头、**折叠完上一步之后**执行，
         所以它发生在 step==BASE 那一行的折叠之后，不是在 BASE-1 的折叠前后随便放。
      2. 冻结点会把 `levels` 用全部预热样本重新表达（`levels=[N-q_j for warm]`），
         不是只追加。
      3. `dN` 里的基准是"当前 `levels` 的上中位"，冻结后 `levels` 被换掉，
         但 `dN` 在冻结点时仍是空的（预热期 age 恒为 0），所以顺序只影响 `levels`。
    """
    levels = []
    dN = collections.defaultdict(list)
    phase_levels = collections.defaultdict(list)
    warm = []
    frozen = False
    offsets = {}
    out = []
    for r in rows:
        # ---- 本步的预测（用冻结点之前的状态）----
        est, src = 0.0, "warmup"
        if r["step"] >= WARM_END and levels:
            a, j = r["age"], r["phase"]
            lvl = levels[-1]

            def pred(keyfn):
                hit = keyfn(a, j)
                if hit:
                    return umed(hit), "hit"
                ks = sorted({k[0] for k, v in dN.items() if v})
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    m2 = umed([x for k, v in dN.items() if k[0] == a2 for x in v])
                    m1 = umed([x for k, v in dN.items() if k[0] == a1 for x in v])
                    sl = (m2 - m1) / max(1e-9, float(a2 - a1))
                    return m2 + sl * (a - a2), "extrap"
                if len(ks) == 1:
                    return umed([x for k, v in dN.items() if k[0] == ks[0] for x in v]), "flat"
                return 0.0, "boot_none"

            keyfn = ((lambda aa, jj: dN.get((aa, -1))) if mode == "old"
                     else (lambda aa, jj: dN.get((aa, jj))))
            d, src = pred(keyfn)
            est = lvl + max(0.0, d)
        out.append({"step": r["step"], "age": r["age"], "phase": r["phase"],
                    "est": est, "avg": r["avg"], "src": src,
                    "est_rec": r["est"], "its": r["its"], "model": r["model"]})
        # ---- 折叠本单元（decide() 开头的折叠，效果等同）----
        N, M = r["its"], r["model"]
        if r["age"] == 0:
            levels.append(M)
            if not frozen and r["step"] < WARM_END:
                phase_levels[r["phase"]].append(N)
                warm.append((N, r["phase"]))
        elif levels:
            base = umed(levels)
            dN[(r["age"], -1) if mode == "old" else (r["age"], r["phase"])].append(M - base)
        # ---- 冻结点：等价于在 step==BASE-1 折叠之后的那次 freezePhaseOffsets() ----
        if r["step"] == WARM_END - 1:
            frozen = True
            if phase_levels.get(0):
                b0 = umed(phase_levels[0])
                for jj, v in phase_levels.items():
                    if v:
                        offsets[jj] = umed(v) - b0
            if any(q != 0 for q in offsets.values()):
                levels = [Nn - offsets.get(jj, 0.0) for Nn, jj in warm]
    return out


# ------------------------------------------------------- Q3: q 误差归因
def q_error_groups(post, fq):
    """把 model_its 的相位主效应按"冻结 q 的误差"分解到三组相位。"""
    byp = collections.defaultdict(list)
    for r in post:
        byp[r["phase"]].append(r["its"])
    if 0 not in byp:
        return None
    need = {j: umed(v) - umed(byp[0]) for j, v in byp.items()}
    err = {j: fq.get(j, 0.0) - need[j] for j in byp}
    groups = [("A_warm_ge15", range(0, 6)), ("B_warm_1to2", range(6, 13)),
              ("C_warm_0", range(13, 16))]
    n = len(post)
    parts = {}
    for name, js in groups:
        js = [j for j in js if j in err]
        if not js:
            continue
        parts[name] = {
            "phases": [min(js), max(js)],
            "n_obs": sum(len(byp[j]) for j in js),
            "rms_err": round((sum(err[j] ** 2 for j in js) / len(js)) ** 0.5, 2),
            "var_share_pct": None,
        }
    tot = sum(parts[k]["n_obs"] * parts[k]["rms_err"] ** 2 for k in parts)
    for k in parts:
        c = parts[k]["n_obs"] * parts[k]["rms_err"] ** 2
        parts[k]["var_share_pct"] = round(100 * c / tot, 1) if tot else None
    sd_pred = (tot / n) ** 0.5
    return {"q_frozen": {str(j): fq.get(j, 0.0) for j in sorted(byp)},
            "q_needed_posthoc": {str(j): round(need[j], 1) for j in sorted(byp)},
            "q_err": {str(j): round(err[j], 1) for j in sorted(byp)},
            "mean_abs_err": round(sum(abs(v) for v in err.values()) / len(err), 2),
            "groups": parts, "sd_from_q_err": round(sd_pred, 2),
            "sd_model_actual": round(st.pstdev([r["model"] for r in post]), 2),
            "sd_posthoc_q": round(st.pstdev(
                [r["its"] - need[r["phase"]] for r in post]), 2)}


# --------------------------------------------------- Q4: 时变还是估不准
def offset_drift(post):
    """控制年龄带与 step 块，看同一相位的偏移到底随谁变。"""
    res = {"by_age_band": {}, "by_step_block": {}, "crosstab": {}}
    cnt = collections.Counter(r["phase"] for r in post if r["phase"] != 0)
    if not cnt:
        return res
    j = cnt.most_common(1)[0][0]
    res["probe_phase"] = j
    for lo, hi in [(1, 10), (11, 25), (26, 45), (46, 70)]:
        seg = [r for r in post if lo <= r["age"] <= hi]
        byp = collections.defaultdict(list)
        for r in seg:
            byp[r["phase"]].append(r["its"])
        if 0 in byp and byp.get(j):
            res["by_age_band"]["%d-%d" % (lo, hi)] = {
                "offset": round(umed(byp[j]) - umed(byp[0]), 1),
                "n": len(byp[j])}
    for lo, hi in [(100, 500), (500, 900), (900, 1300), (1300, 1800)]:
        seg = [r for r in post if lo <= r["step"] < hi]
        byp = collections.defaultdict(list)
        for r in seg:
            byp[r["phase"]].append(r["its"])
        if 0 in byp and byp.get(j):
            res["by_step_block"]["%d-%d" % (lo, hi)] = {
                "offset": round(umed(byp[j]) - umed(byp[0]), 1),
                "n": len(byp[j])}
    # 交叉表：同一年龄带内跨 step 块
    for lo, hi in [(1, 15), (16, 35), (36, 60), (61, 99)]:
        row = {}
        for slo, shi in [(100, 500), (500, 900), (900, 1300), (1300, 1800)]:
            seg = [r for r in post if slo <= r["step"] < shi and lo <= r["age"] <= hi]
            byp = collections.defaultdict(list)
            for r in seg:
                byp[r["phase"]].append(r["its"])
            if 0 in byp and byp.get(j):
                row["step%d-%d" % (slo, shi)] = {
                    "offset": round(umed(byp[j]) - umed(byp[0]), 1), "n": len(byp[j])}
        res["crosstab"]["age%d-%d" % (lo, hi)] = row
    return res


# --------------------------------------------- Q4b: 在线更新 q 能否补救
def causal_split(post):
    """在 post 前半段估 q_j，在后半段评估。与"用预热 q"对照。"""
    if len(post) < 100:
        return None
    half = len(post) // 2
    tr, te = post[:half], post[half:]

    def qof(rs):
        byp = collections.defaultdict(list)
        for r in rs:
            byp[r["phase"]].append(r["its"])
        if not byp:
            return {}
        key = 0 if 0 in byp else min(byp)
        base = umed(byp[key])
        return {j: umed(v) - base for j, v in byp.items()}

    def score(q, label):
        vals, miss = [], 0
        for r in te:
            if r["phase"] in q:
                vals.append(r["its"] - q[r["phase"]])
            else:
                vals.append(r["its"])
                miss += 1
        return {"label": label, "sd": round(st.pstdev(vals), 2),
                "coverage_pct": round(100 * (len(vals) - miss) / len(vals), 0),
                "n": len(vals)}

    return {"n_eval": len(te),
            "from_warmup": score(qof([r for r in post if r["step"] <= WARM_END]) or {}, "warmup"),
            "from_first_half": score(qof(tr), "post_first_half"),
            "posthoc_upper_bound": score(qof(te), "in_sample_upper_bound")}


def main():
    out = {"_note": "R-02 离线裁决；未跑求解器、未改 pbr_policy.h", "cases": {}}
    for case in CASES:
        for arm in ARMS:
            path = os.path.join(BASE, case, arm, "trace.csv")
            if not os.path.exists(path):
                continue
            rows = load(path)
            wk, post = split(rows)
            if not post or len(post) < 50:
                continue
            fq = frozen_q(rows, wk)
            rec = {"n_post_age_ge1": len(post),
                   "n_phases": len({r["phase"] for r in post})}

            # Q1/Q3：92.3% 是观测量还是预测器
            need = None
            byp = collections.defaultdict(list)
            for r in post:
                byp[r["phase"]].append(r["its"])
            if 0 in byp:
                base = umed(byp[0])
                need = {j: umed(v) - base for j, v in byp.items()}
                for r in post:
                    r["its_m"] = r["its"] - need[r["phase"]]
            rec["two_way"] = {"its": two_way(post, "its"),
                              "model_its_frozen_q": two_way(post, "model")}
            if need:
                rec["two_way"]["its_minus_posthoc_q"] = two_way(post, "its_m")

            # Q3：q 误差归因
            rec["q_attribution"] = q_error_groups(post, fq)

            # Q2：换键重放
            old = replay(rows, "old")
            ajan = replay(rows, "ajan")
            ok = sum(1 for o in old if abs(o["est"] - o["est_rec"]) < 1e-6)
            live = [i for i, o in enumerate(old) if o["est"] > 0]
            flips = sum(1 for i in live
                        if (ajan[i]["est"] > ajan[i]["avg"]) != (old[i]["est"] > old[i]["avg"]))
            # 误差必须在 model 尺度上比：est = lvl + max(0,delta) 与 model_its 同尺度。
            # 早先版本拿 est 减原始 its，混了两个尺度，读数无意义。
            mae_old = sum(abs(old[i]["model"] - old[i]["est"]) for i in live) / len(live)
            mae_new = sum(abs(ajan[i]["model"] - ajan[i]["est"]) for i in live) / len(live)
            bias_old = sum(old[i]["model"] - old[i]["est"] for i in live) / len(live)
            bias_new = sum(ajan[i]["model"] - ajan[i]["est"] for i in live) / len(live)
            hit_old = sum(1 for i in live if old[i]["src"] == "hit") / len(live)
            hit_new = sum(1 for i in live if ajan[i]["src"] == "hit") / len(live)
            n_diff = sum(1 for i in live if abs(old[i]["est"] - ajan[i]["est"]) > 1e-9)
            rec["abin_replay"] = {
                "replay_fidelity_pct": round(100 * ok / len(old), 1),
                "n_live": len(live),
                "n_pred_differs": n_diff,
                "mae_old_model_scale": round(mae_old, 3),
                "mae_ajan_model_scale": round(mae_new, 3),
                "mae_change_pct": round(100 * (mae_new - mae_old) / mae_old, 1),
                "bias_old": round(bias_old, 2), "bias_ajan": round(bias_new, 2),
                "hit_rate_old_pct": round(100 * hit_old, 0),
                "hit_rate_ajan_pct": round(100 * hit_new, 0),
                "decision_flips": flips, "decision_flip_pct": round(100 * flips / len(live), 1),
            }

            # Q4：时变 vs 估不准
            rec["offset_drift"] = offset_drift(post)
            rec["causal_split"] = causal_split(post)
            out["cases"]["%s/%s" % (case, arm)] = rec

            print("=== %s/%s  post n=%d  相位 %d" % (case, arm, len(post), rec["n_phases"]))
            print("  两因子: its=%s" % (rec["two_way"]["its"],))
            print("          model_its=%s" % (rec["two_way"]["model_its_frozen_q"],))
            if need:
                print("          its-事后q=%s" % (rec["two_way"]["its_minus_posthoc_q"],))
            qa = rec["q_attribution"]
            if qa:
                print("  q 误差 平均 %.2f  SD由q误差 %.2f (实测 %.2f, 事后真值 %.2f)" % (
                    qa["mean_abs_err"], qa["sd_from_q_err"], qa["sd_model_actual"],
                    qa["sd_posthoc_q"]))
                for k, v in qa["groups"].items():
                    print("    %-12s 相位%s n=%-4d RMS=%5.2f 占 %s%%" % (
                        k, v["phases"], v["n_obs"], v["rms_err"], v["var_share_pct"]))
            ab = rec["abin_replay"]
            print("  换键重放(保真 %.1f%%): 预测变化的行 %d/%d  MAE(model尺度) %.3f->%.3f (%+.1f%%)" % (
                ab["replay_fidelity_pct"], ab["n_pred_differs"], ab["n_live"],
                ab["mae_old_model_scale"], ab["mae_ajan_model_scale"], ab["mae_change_pct"]))
            print("            命中 %.0f%%->%.0f%%  偏差 %+.2f->%+.2f  决策翻转 %d (%.1f%%)" % (
                ab["hit_rate_old_pct"], ab["hit_rate_ajan_pct"],
                ab["bias_old"], ab["bias_ajan"],
                ab["decision_flips"], ab["decision_flip_pct"]))
            od = rec["offset_drift"]
            if od.get("by_step_block"):
                print("  偏移随 step: %s" % od["by_step_block"])
            cs = rec["causal_split"]
            if cs:
                print("  因果分割: 预热q SD=%.2f(覆盖%.0f%%)  前半q SD=%.2f(覆盖%.0f%%)  事后 SD=%.2f" % (
                    cs["from_warmup"]["sd"], cs["from_warmup"]["coverage_pct"],
                    cs["from_first_half"]["sd"], cs["from_first_half"]["coverage_pct"],
                    cs["posthoc_upper_bound"]["sd"]))
            print()

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
