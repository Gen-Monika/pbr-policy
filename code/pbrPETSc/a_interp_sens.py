#!/usr/bin/env python3
"""插值口径敏感性：linear vs step 下各配置的 regret（含 l15 诊断）"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"


def load(parts):
    cells = defaultdict(list); rv = []; fac = []
    for prefix, logdir, Ks, rounds in parts:
        for K in Ks:
            for R in rounds:
                c = "%s_pc_k%d_r%d.csv" % (prefix, K, R)
                l = os.path.join(logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
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
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac),
                nsteps=max(t for t, a in cells))


M = {
    "fx":  [("fx", "%s/fixed" % P2, [1,2,3,5,8], [1,2,3,4,5]),
            ("covscan_l10", "%s/covscan_l10" % P2, [13,20,30], [1,2,3])],
    "l15": [("l15", "%s/l15" % P2, [1,2,3,5,8], [1,2,3,4,5]),
            ("cov2_l15", "%s/cov2_l15" % P2, [13,20,30], [1,2,3])],
    "l20": [("l20", "%s/l20" % P2, [1,2,3,5,8], [1,2,3,4,5]),
            ("covscan_l20", "%s/covscan_l20" % P2, [13,20,30], [1,2,3])],
}

print("=" * 100)
print("★★★ 插值口径敏感性 + 最优 K* 的稳定性")
print("=" * 100)
print("  %-6s %-8s %12s %10s %10s %10s" % ("配置", "插值", "oracle", "K*", "在线", "在线−K*"))
for tag in ("fx", "l15", "l20"):
    cfg = load(M[tag]); T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    for ip in ("linear", "step"):
        env = P.Env(cfg["tab"], mode="real", interp=ip)
        Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data+1)
        orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        kb = info["Kbest"]
        onl = 100*(info["online"]/orc-1); kk = 100*(info["fixed"][kb]/orc-1)
        print("  %-6s %-8s %12.0f %9.2f%% %9.2f%% %+9.2f pp" % (tag, ip, orc, kk, onl, onl-kk))

print()
print("=" * 100)
print("★★★ l15 的在线轨迹：到底重建了多少次、间隔多长")
print("=" * 100)
cfg = load(M["l15"]); T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
for ip in ("linear", "step"):
    env = P.Env(cfg["tab"], mode="real", interp=ip)
    Ks = tuple(k for k in (1,2,3,4,5,6,8,10,13,20,30) if k <= env.amax_data+1)
    orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
    # 重新跑一遍在线并记录重建时刻
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1; rs = []
    for t in range(1, T+1):
        if t < P.B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                else:
                    delta = st.median(know[ks[-1]])
            else:
                delta = 0.0
            rebuild = (lvl + max(0.0, delta)) > avg
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < P.B0 else (c, 1)
            levels.append(N); a = 1; held = t; rs.append(t)
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    post = [t for t in rs if t > P.B0]
    gaps = [post[i+1]-post[i] for i in range(len(post)-1)]
    from collections import Counter
    print("\n  [%s]  在线 regret=%.2f%%  重建 %d 次（预热后 %d 次）"
          % (ip, 100*(tot/orc-1), len(rs), len(post)))
    print("       预热后重建间隔分布: %s" % dict(sorted(Counter(gaps).items())))
    print("       最后 20 个重建时刻: %s" % post[-20:])
    print("       know 表: %s" % {k: (len(v), round(st.median(v),1)) for k, v in sorted(know.items()) if v})
