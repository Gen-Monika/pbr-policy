#!/usr/bin/env python3
"""
★★★ a_cost_eval.py —— 机器无关指标 cost(π; ρ) 的统一评估（含审计）

落实顺序第 1 步。★ 2026-10-12 审计后修正：
  · ρ 按配置标定（取该配置实测 r1 = median(tPCSetup/tIter)），不再全局取 60
    —— 全局 ρ 会让 fl30 的模型重建次数偏离 34%，看起来像模型坏了（陷阱 50）
  · A4 拆成两层：决策序列一致率（应 100%）+ 累计 iters 相对差（应 <0.1%）
    —— 不用"逐步逐位一致"当判据（陷阱 49）

用法：
  python a_cost_eval.py                # 全量
  python a_cost_eval.py --audit         # 只跑审计
  python a_cost_eval.py --tag l20       # 单配置
"""
import sys, os, json, glob, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
from pbrcost import (CFG, ORDER, PHASE_A, PHASE_K, load_phase, Env,
                     sim_fixed, sim_online, sim_online_detail, sim_dp,
                     rho_interval_from_order, rho_interval_calib, audit_all,
                     rho_sweep, _rows, _per_step_N, P2)

ONLY = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else None
AUDIT_ONLY = "--audit" in sys.argv

# 实测运行：前缀 → (case 目录, 各 mode 的 iters)
RUNS = {
    "l15":  ("a2l15", {"K1": 5765, "K3": 10335, "ONLs": 8040, "ONLp": 10544}),
    "l20":  ("a2A",   {"K1": 4688, "K3": 9361, "K5": 16046, "ONLs": 6940, "ONLp": 9474}),
    "fl30": ("a2B",   {"K1": 11953, "K3": 26373, "K5": 52114, "ONLs": 26648, "ONLp": 37696}),
}
KsAll = (1, 2, 3, 4, 5, 6, 8, 10, 13, 20, 30)


def online_path(env, rho, T, B0, stop=None, step_cost=False):
    """★ 委托给 pbrcost.sim_online_detail —— 不得重写策略逻辑。
    重复实现曾导致真实缺陷（平均口径写成纯迭代数，决策一致率 29%）。"""
    from pbrcost import sim_online_detail
    return sim_online_detail(env, rho, T, B0, stop=stop, step_cost=step_cost)


def meas_path(tag, mode):
    """从实测 pc CSV + log 取 (逐步动作, 逐步 N, 最大年龄)。"""
    pre = RUNS[tag][0]
    pc = "%s/%s_pc_%s_r1.csv" % (P2, pre, mode)
    lg = "%s/%s_case/log.%s.r1" % (P2, pre, mode)
    if not (os.path.exists(pc) and os.path.exists(lg)): return None
    rr = _rows(pc); seen = {}
    for x in rr:
        if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
            seen[int(x["timeIndex"])] = x
    steps = [seen[t] for t in sorted(seen)]
    Ns = _per_step_N(lg); n = min(len(steps), len(Ns))
    act = [int(steps[i]["reusedFrom"]) < 0 for i in range(n)]
    ages = []
    held = -1
    for i in range(n):
        if act[i]: ages.append(0); held = i + 1
        else: ages.append(i + 1 - held)
    return dict(act=act, N=Ns[:n], ages=ages, n=n,
                it=sum(Ns[:n]), rb=sum(1 for a in act if a))


def audit_cfg(tag):
    """对单个配置做分层审计。返回 dict。"""
    d = load_phase(tag)
    if d is None: return None
    lvl, T, B0 = CFG[tag]
    env = Env(d["tab"], sFact=d.get("s", 1.0))
    r1 = d["r1"]
    out = dict(tag=tag, lvl=lvl, T=T, B0=B0, nfile=d["nfile"],
               ncell=len(d["tab"]), amax=env.amax_data, r1=r1, s=d["s"],
               ages=sorted(set(a for _, a in d["tab"])))

    # A0 Env 互证（对 pbrlib）
    try:
        import pbrlib
        eo = pbrlib.Env(d["tab"], interp="shape")
        bad = sum(1 for t in range(1, T + 1)
                  for a in range(0, env.amax_data + 1)
                  if abs(env(t, a) - eo(t, a)) > 1e-9)
        out["env_diff"] = bad
    except Exception as e:
        out["env_diff"] = "n/a(%s)" % e

    # A1/A2/A3（内建）
    ok, msgs = audit_all(dict(env=env), r1, T, B0)
    out["builtin_ok"] = ok; out["builtin_msgs"] = msgs

    # A4 分层
    rows = []
    if tag in RUNS:
        for m in sorted(RUNS[tag][1]):
            mp = meas_path(tag, m)
            if not mp: continue
            n = mp["n"]
            if m.startswith("K") and m[1:].isdigit():
                K = int(m[1:])
                pred = [(t < B0 or (t - B0) % K == 0) for t in range(1, n + 1)]
                # 模型沿实测路径的值
                mv = []
                held = -1
                for t in range(1, n + 1):
                    if mp["act"][t - 1]: mv.append(env(t, 0)); held = t
                    else: mv.append(env(t, t - held))
            else:
                # ONLp 走 RCOST=step 口径：一次重建记 s·ρ
                sc = (m == "ONLp")
                c_, it_, rb_, pred, mv = online_path(env, r1, T, B0, stop=n, step_cost=sc)
            agr = 100.0 * sum(1 for i in range(n) if pred[i] == mp["act"][i]) / n
            step_id = 100.0 * sum(1 for i in range(n) if mv[i] == mp["N"][i]) / n
            rel = 100.0 * (sum(mv) - mp["it"]) / mp["it"]
            rows.append(dict(mode=m, n=n, maxage=max(mp["ages"]),
                             meas_it=mp["it"], mod_it=sum(mv),
                             meas_rb=mp["rb"], mod_rb=sum(1 for x in pred if x),
                             act_agr=agr, step_id=step_id, it_rel_pct=rel))
    out["per_mode"] = rows
    return out


def main():
    tags = [ONLY] if ONLY else list(ORDER)
    print("=" * 122)
    print("★★★ cost(π; ρ) = iters(π) + ρ · rbsteps(π)   机器无关指标 · 分层审计")
    print("=" * 122)
    audit = {}
    for tag in tags:
        a = audit_cfg(tag)
        if a is None:
            print("\n【%s】★ 无相位数据" % tag); continue
        audit[tag] = a
        print("\n" + "─" * 122)
        print("【%s】levels=%d T=%d B0=%d | 相位 %d 文件 %d 格子 年龄=%s"
              % (tag, a["lvl"], a["T"], a["B0"], a["nfile"], a["ncell"], a["ages"]))
        print("  amax_data=%d  ρ(=实测 r1)=%.1f  s=%.2f  Env 对 pbrlib 不一致=%s 处"
              % (a["amax"], a["r1"], a["s"], a["env_diff"]))
        print("  内建 A1–A3: %s" % ("通过" if a["builtin_ok"] else "★未通过"))
        for m in a["builtin_msgs"]:
            if not m.startswith("A1–A4"): print("     " + m)
        if a["per_mode"]:
            print("  A4 分层审计：")
            print("    %-6s %-6s %-10s %-10s %-10s %-10s %s"
                  % ("mode", "maxage", "实测(it,rb)", "模型(it,rb)", "决策一致", "逐步一致", "iters相对差"))
            for r in a["per_mode"]:
                flag = "" if r["act_agr"] > 99.99 else "  ★决策不一致"
                print("    %-6s %-6d (%6d,%4d) (%6d,%4d) %8.2f%% %8.2f%% %+9.4f%%%s"
                      % (r["mode"], r["maxage"], r["meas_it"], r["meas_rb"],
                         r["mod_it"], r["mod_rb"], r["act_agr"], r["step_id"],
                         r["it_rel_pct"], flag))

    if AUDIT_ONLY:
        with open("%s/cost_eval_audit.json" % P2, "w") as f:
            json.dump(audit, f, indent=1, default=str)
        print("\n已写出 cost_eval_audit.json")
        return

    # ── ρ 网格扫描
    print("\n" + "=" * 122)
    print("★★★ 第 2 步：ρ 网格上的 cost 评估（★ 覆盖该配置的【物理区间】[r1, s·r1]）")
    print("=" * 122)
    # ★ 2026-10-13 修正：原先只用 r1 的 0.5–3× 相对网格，与物理区间不对齐。
    #   正确口径是覆盖 [r1, s·r1]，并向外各留 0.5× 作为稳健性余量。
    allrows = []
    for tag in tags:
        if tag not in audit: continue
        a = audit[tag]
        d = load_phase(tag); lvl, T, B0 = CFG[tag]; env = Env(d["tab"], sFact=d.get("s", 1.0))
        r1 = a["r1"]; sfac = d.get("s", 1.0)
        rlo, rhi = rho_interval_calib(r1, sfac)
        grid = sorted(set([max(5, int(round(rlo * 0.5))), int(round(rlo))]
                          + [int(round(rlo + (rhi - rlo) * i / 6.0)) for i in range(7)]
                          + [int(round(rhi)), int(round(rhi * 1.5))]))
        print("\n  【%s】ρ 物理区间 = [%.1f, %.1f]（r1=%.1f, s=%.2f）  T=%d B0=%d  amax_data=%d"
              % (tag, rlo, rhi, r1, sfac, T, B0, env.amax_data))
        print("  %6s %8s %6s %11s %11s %11s %10s %9s"
              % ("ρ", "ρ/r1", "K*", "cost(K*)", "cost(在线)", "cost(oracle)", "在线gap%", "regret%"))
        for r in grid:
            s = rho_sweep(dict(env=env), [r], T, B0)[r]
            if abs(s["kk"][0]) < 1e-12: continue
            gap = 100.0 * (s["onl"][0] / s["kk"][0] - 1.0)
            reg = 100.0 * (s["onl"][0] / s["orc"][0] - 1.0)
            mark = ""
            if abs(r - rlo) <= 1: mark = "  <- 下界 r1"
            elif abs(r - rhi) <= 1: mark = "  <- 上界 s*r1"
            print("  %6d %8.2f %6s %11.0f %11.0f %11.0f %9.3f%% %8.2f%%%s"
                  % (r, r / r1, "K%d" % s["kb"], s["kk"][0], s["onl"][0],
                     s["orc"][0], gap, reg, mark))
            allrows.append(dict(tag=tag, rho=r, rho_over_r1=r / r1,
                                in_phys_interval=(rlo - 0.5 <= r <= rhi + 0.5),
                                kstar=s["kb"],
                                c_kstar=s["kk"][0], c_online=s["onl"][0],
                                c_oracle=s["orc"][0], it_onl=s["onl"][1],
                                rb_onl=s["onl"][2], it_kst=s["kk"][1],
                                rb_kst=s["kk"][2], gap_pct=gap, regret_pct=reg))

    with open("%s/cost_eval.json" % P2, "w") as f:
        json.dump(dict(audit=audit, rows=allrows), f, indent=1, default=str)
    print("\n已写出 cost_eval.json（%d 行）" % len(allrows))
    print("=" * 122)


main()
