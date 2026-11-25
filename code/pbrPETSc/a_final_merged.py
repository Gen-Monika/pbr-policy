#!/usr/bin/env python3
"""
★★★ A-终（修正版）：显式 CSV 前缀映射 + 覆盖补足后的主结果

═══ 相对 coverage_final.py 的修正 ═══
那个版本用 os.path.basename(logdir) 当 CSV 前缀，而：
    fixed/  目录 → CSV 前缀是 "fx"    ✗ 不匹配，静默丢掉了全部 K=1..8
    l20/    目录 → CSV 前缀是 "l20"   ✓ 恰好一致，未受影响
⇒ fx 的结果是错的（只剩 covscan 的 K=13/20/30）。
本版本用显式 (csv_prefix, logdir) 映射，并在加载后【强制核对键数】。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, ".")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"


def tbl(parts, verbose=True):
    """parts = [(csv_prefix, logdir, Ks, rounds), ...]"""
    cells = defaultdict(list); rv = []; fac = []
    per_part = {}
    for prefix, logdir, Ks, rounds in parts:
        got = 0
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                rr = [seen[t] for t in sorted(seen)]
                Ns = P.per_step_N(l); n = min(len(rr), len(Ns))
                for i in range(n):
                    x = rr[i]; t = i + 1
                    rf = int(x["reusedFrom"])
                    cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
                allr = P.rows(c)
                for x in allr:
                    if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                        rv.append(x["tPCSetup"]/x["tIter"])
                    rbs = None
                got += 1
        per_part[(prefix, logdir)] = got
    if verbose:
        for k, v in per_part.items():
            flag = "OK" if v > 0 else "★ 空！"
            print("      载入 %-24s %-30s 文件数=%d %s" % (k[0], k[1], v, flag))
    if not cells: return None
    # 每步分解次数
    fac = []
    for prefix, logdir, Ks, rounds in parts:
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
                if not os.path.exists(c): continue
                allr = P.rows(c)
                rbs = set(int(x["timeIndex"]) for x in allr if int(x["reused"]) == 0)
                nrs = sum(1 for x in allr if int(x["reused"]) == 0)
                if rbs: fac.append(nrs/len(rbs))
    nsteps = max(t for (t, a) in cells)
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac) if fac else 1.0, nsteps=nsteps)


MERGED = {
    "fx":  [("fx",          "%s/fixed" % P2,        [1,2,3,5,8], [1,2,3,4,5]),
            ("covscan_l10", "%s/covscan_l10" % P2,  [13,20,30],  [1,2,3])],
    "l20": [("l20",         "%s/l20" % P2,          [1,2,3,5,8], [1,2,3,4,5]),
            ("covscan_l20", "%s/covscan_l20" % P2,  [13,20,30],  [1,2,3])],
}

print("=" * 118)
print("★★★ A-终（修正版）：覆盖补足后的主结果")
print("=" * 118)
res = {}
for tag in ("fx", "l20"):
    print("\n[%s] 加载" % tag)
    cfg = tbl(MERGED[tag])
    if cfg is None:
        print("  加载失败"); continue
    T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
    env = P.Env(cfg["tab"], mode="real", interp="linear")
    Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data+1)
    print("  T=%d  r_solve=%.2f  每步分解=%.2f  r_eff=%.1f  amax_data=%d"
          % (T, cfg["r1"], cfg["fac"], r0, env.amax_data))
    try:
        orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
    except AssertionError as e:
        print("  自检失败: %s" % e); continue
    kb = info["Kbest"]
    print("\n  %-6s %12s %11s %10s" % ("K", "成本", "每步", "regret"))
    for K in Ks:
        c = info["fixed"][K]
        print("  %-6s %12.0f %11.1f %9.2f%%%s"
              % (K, c, c/T, 100*(c/orc-1), " ← 最优" if K == kb else ""))
    print("  %-6s %12.0f %11.1f %9.2f%%  ← oracle" % ("orc", orc, orc/T, 0.0))
    print("  %-6s %12.0f %11.1f %9.2f%%  ← 在线"
          % ("在线", info["online"], info["online"]/T, 100*(info["online"]/orc-1)))
    res[tag] = (orc, info, kb, T, r0)

print("\n" + "=" * 118)
print("★★★ 汇总（覆盖补足后）")
print("=" * 118)
print("  %-6s %8s %12s %12s %12s %12s %10s" %
      ("配置","r_eff","K=1","最优K*","oracle","在线","在线vsK*"))
for tag, (orc, info, kb, T, r0) in res.items():
    print("  %-6s %8.1f %11.2f%% %11.2f%% %11.2f%% %11.2f%% %+9.2f pp"
          % (tag, r0, 100*(info["fixed"][1]/orc-1),
             100*(info["fixed"][kb]/orc-1), 0.0,
             100*(info["online"]/orc-1),
             100*(info["online"]/orc-1) - 100*(info["fixed"][kb]/orc-1)))
