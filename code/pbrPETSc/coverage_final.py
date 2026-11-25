#!/usr/bin/env python3
"""
★★★ A-终：覆盖补足后的主结果（age 覆盖到 30，是 K* 的 5–15 倍）

═══ 相对 rerun_main.py 的唯一区别 ═══
把 covscan 的 K ∈ {13,20,30} 合并进来，使 age 覆盖从 7 提到 30。
⇒ 插值口径的影响应当显著缩小（此前 25–60 pp）——
  因为"最优 K* 附近的年龄"现在完全落在实测区内。
"""
import sys, os, re, statistics as st
from collections import defaultdict
sys.path.insert(0, ".")
import pbrlib as P

# ---------- 合并加载：把多批 (logdir, Ks) 拼成一张表 ----------
def load_merged(parts):
    """parts = [(logdir, Ks, rounds), ...] → 与 P.load_config 同结构"""
    cells = defaultdict(list); rv = []; fac = []; ns = None
    for logdir, Ks, rounds in parts:
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (os.path.basename(logdir), K, R)
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)):
                    continue
                rr = P.rows(c); seen = {}
                for d in rr:
                    if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
                        seen[int(d["timeIndex"])] = d
                rr = [seen[t] for t in sorted(seen)]
                Ns = P.per_step_N(l); n = min(len(rr), len(Ns))
                if ns is None or n > ns: ns = n
                for i in range(n):
                    d = rr[i]; t = i + 1
                    rf = int(d["reusedFrom"])
                    cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
                allr = P.rows(c)
                for d in allr:
                    if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                        rv.append(d["tPCSetup"]/d["tIter"])
                rbs = set(int(d["timeIndex"]) for d in allr if int(d["reused"]) == 0)
                nrs = sum(1 for d in allr if int(d["reused"]) == 0)
                if rbs: fac.append(nrs/len(rbs))
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


P2 = "/root/autodl-tmp/PBR"
R0 = [1,2,3,4,5]
RC = [1,2,3]

MERGED = {
    "fx":  [("%s/fixed" % P2,   [1,2,3,5,8], R0),
            ("%s/covscan_l10" % P2, [13,20,30], RC)],
    "l20": [("%s/l20" % P2,     [1,2,3,5,8], R0),
            ("%s/covscan_l20" % P2, [13,20,30], RC)],
}

print("=" * 120)
print("★★★ A-终：覆盖补足后的主结果")
print("=" * 120)

for tag in ("fx", "l20"):
    cfg = load_merged(MERGED[tag])
    if cfg is None:
        print("[%s] 合并失败" % tag); continue
    T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
    print("\n" + "#" * 120)
    print("#  [%s]  T=%d  r_eff=%.1f  每步分解=%.2f" % (tag, T, r0, cfg["fac"]))
    print("#" * 120)

    for interp in ("linear", "step"):
        env = P.Env(cfg["tab"], mode="real", interp=interp)
        Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data+1)
        try:
            orc, info = P.selfcheck(env, r0, T, label="%s/%s" % (tag, interp), Ks=Ks)
        except AssertionError as e:
            print("  [%s] 自检失败: %s" % (interp, e)); continue
        kb = info["Kbest"]
        onl = info["online"]
        print("\n  --- 插值 %s ---  amax_data=%d  AMAX=%d  候选K=%s"
              % (interp, env.amax_data, env.amax_data+1, list(Ks)))
        print("  %-8s %12s %12s %10s" % ("K", "成本", "每步", "regret"))
        for K in Ks:
            c = info["fixed"][K]
            mark = " ← 最优" if K == kb else ""
            print("  %-8s %12.0f %12.1f %9.2f%%%s"
                  % (K, c, c/T, 100*(c/orc-1), mark))
        print("  %-8s %12.0f %12.1f %9.2f%%  ← oracle(DP)" % ("oracle", orc, orc/T, 0.0))
        print("  %-8s %12.0f %12.1f %9.2f%%  ← 本文在线"
              % ("在线", onl, onl/T, 100*(onl/orc-1)))
        print("  ⇒ 每步重建 regret %.2f%%   最优 K*=%d (%.2f%%)   在线 %.2f%%"
              % (100*(info["fixed"][1]/orc-1), kb,
                 100*(info["c_fixed_kb"]/orc-1) if "c_fixed_kb" in info
                 else 100*(info["fixed"][kb]/orc-1), 100*(onl/orc-1)))

print("\n" + "=" * 120)
print("★★★ 覆盖补足前后：插值敏感性的对比")
print("=" * 120)
print("  （此前 age 覆盖到 7；现在覆盖到 30）")
print("  %-6s %14s %14s %14s %14s" %
      ("配置","K=1(step)","K=1(linear)","差(前)","差(后)"))
for tag in ("fx", "l20"):
    cfg = load_merged(MERGED[tag])
    T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
    res = {}
    for interp in ("linear", "step"):
        env = P.Env(cfg["tab"], mode="real", interp=interp)
        Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data+1)
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
            res[interp] = 100*(info["fixed"][1]/orc-1)
        except AssertionError:
            res[interp] = None
    d = (res.get("step") - res.get("linear")) if (res.get("step") and res.get("linear")) else None
    print("  %-6s %14s %14s %14s %14s"
          % (tag, ("%.2f%%" % res["step"]) if res.get("step") else "—",
             ("%.2f%%" % res["linear"]) if res.get("linear") else "—",
             "—（前值 25–29 pp）", ("%.2f pp" % d) if d is not None else "—"))
