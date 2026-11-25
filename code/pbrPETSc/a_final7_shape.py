#!/usr/bin/env python3
"""
★★★ A-终（定稿版，2026-10-12）

═══ 与之前所有版本的区别 ═══
1. 填充口径定为 "shape"（形状迁移）—— 见 pbrlib 模块头与
   docs/shape_transfer_decision_2026-10-12.md
2. 显式 (csv_prefix, logdir) 映射（修掉 basename 不匹配导致静默丢文件的 bug）
3. 强制核对每个批次实际载入的文件数
4. 截断文件按 cov2_manifest.json 的判定剔除（政策 B）
5. 全部策略走 pbrlib 的 sim_dp / sim_fixed / sim_online + selfcheck()
6. 同时报告 "shape" 与 "linear" 两种口径，做敏感性对照
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 配置 → (基准步数, [(prefix, logdir, Ks, rounds), ...])
SPEC = {
    "fx":   (344,  [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])]),
    "l15":  (344,  [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
                    ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])]),
    "l20":  (344,  [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])]),
    "fine": (720,  [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
                    ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])]),
    "x3":   (1231, [("x3", "x3run", [1,2,3,5,8], [1,2]),
                    ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])]),
    "fl30": (720,  [("fl30", "fl30run", [1,3,5], [1,2]),
                    ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])]),
    "sth":  (5866, [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
                    ("cov2_sth", "cov2_sth", [20,30], [1,2,3])]),
}


def load(tag, policy="B", verbose=True):
    """policy B = 剔除 nstep < 基准 的截断文件。"""
    base_n = SPEC[tag][0]
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    counts = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        got = 0; skipped = 0
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
                if policy == "B" and len(steps) < base_n:
                    skipped += 1; continue
                Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
                for i in range(n):
                    x = steps[i]; rf = int(x["reusedFrom"])
                    cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
                for x in rr:
                    if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                        rv.append(x["tPCSetup"]/x["tIter"])
                rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                if rbs: fac.append(nrs/len(rbs))
                ns = max(ns, len(steps)); got += 1
        counts.append((prefix, got, skipped, len(Ks)*len(rounds)))
    if verbose:
        for p, g, sk, e in counts:
            flag = "★空" if g == 0 else ("（剔除截断 %d）" % sk if sk else "")
            print("      载入 %-14s %2d/%-2d %s" % (p, g, e, flag))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac), nsteps=ns)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 132)
print("★★★ A-终（定稿）：七配置 · 填充口径 shape（形状迁移）")
print("=" * 132)

RES = {}
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    print("\n" + "#" * 132)
    print("#  [%s]" % tag)
    print("#" * 132)
    cfg = load(tag)
    if cfg is None:
        print("  ★ 无数据"); continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    for interp in ("shape", "linear"):
        env = P.Env(cfg["tab"], mode="real", interp=interp)
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: continue
        try:
            orc, info = P.selfcheck(env, r0, T, label="%s/%s" % (tag, interp), Ks=Ks)
        except AssertionError as e:
            print("  [%s] ★自检失败: %s" % (interp, str(e)[:70])); continue
        kb = info["Kbest"]
        kk = 100*(info["fixed"][kb]/orc-1); onl = 100*(info["online"]/orc-1)
        RES[(tag, interp)] = dict(T=T, amax=env.amax_data, r0=r0, orc=orc,
                                  kb=kb, kk=kk, onl=onl, gap=onl-kk,
                                  k1=100*(info["fixed"][1]/orc-1),
                                  info=info, env=env)
        if interp == "shape":
            print("  T=%d  r_eff=s·r=%.1f  s=%.2f  r=%.2f  amax_data=%d  候选K=%s"
                  % (T, r0, cfg["fac"], cfg["r1"], env.amax_data, list(Ks)))
            print()
            print("  %-8s %14s %12s %11s" % ("K", "总成本", "每步", "相对oracle"))
            for K in Ks:
                c = info["fixed"][K]
                print("  %-8s %14.0f %12.1f %10.2f%%%s"
                      % (K, c, c/T, 100*(c/orc-1), "  ← 最优 K*" if K == kb else ""))
            print("  %-8s %14.0f %12.1f %10.2f%%  ← oracle(DP)" % ("oracle", orc, orc/T, 0.0))
            print("  %-8s %14.0f %12.1f %10.2f%%  ← 本文在线"
                  % ("在线", info["online"], info["online"]/T, onl))
            print()
        print("  [%-6s] oracle=%9.0f  K*=%2d (%6.2f%%)  在线 %6.2f%%  在线−K* %+7.2f pp"
              % (interp, orc, kb, kk, onl, onl-kk))

print("\n" + "=" * 132)
print("★★★ 汇总（shape 口径为准；linear 列出以显示敏感性）")
print("=" * 132)
hdr = ("  %-6s %8s %6s %7s %8s %10s %9s %9s %9s %10s %10s"
       % ("配置", "r_eff", "amax", "T", "K*", "K=1", "K*", "在线", "在线−K*", "linear差", "自检"))
print(hdr)
gaps = []; onls = []; kks = []
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    s = RES.get((tag, "shape")); l = RES.get((tag, "linear"))
    if not s:
        print("  %-6s  ★无 shape 结果" % tag); continue
    gaps.append(s["gap"]); onls.append(s["onl"]); kks.append(s["kk"])
    ld = "%+.2f pp" % (s["gap"] - l["gap"]) if l else "★崩"
    print("  %-6s %8.1f %6d %7d %8d %9.2f%% %8.2f%% %8.2f%% %+9.2f %10s %10s"
          % (tag, s["r0"], s["amax"], s["T"], s["kb"], s["k1"], s["kk"],
             s["onl"], s["gap"], ld, "OK"))

if gaps:
    print()
    print("  在线 regret      中位 %6.2f%%  范围 [%6.2f%%, %6.2f%%]" % (st.median(onls), min(onls), max(onls)))
    print("  最优 K* regret   中位 %6.2f%%  范围 [%6.2f%%, %6.2f%%]" % (st.median(kks), min(kks), max(kks)))
    print("  在线 − K*        中位 %+6.2f pp  范围 [%+6.2f, %+6.2f] pp" % (st.median(gaps), min(gaps), max(gaps)))
    print("  ★ 在线优于 K* 的配置数：%d / %d" % (sum(1 for g in gaps if g < 0), len(gaps)))
    print()
    print("  K* 分布：%s" % ", ".join("%s:K*=%d" % (t, RES[(t,"shape")]["kb"])
                                    for t in ("fx","l15","l20","fine","x3","fl30","sth")
                                    if (t,"shape") in RES))
print("=" * 132)
