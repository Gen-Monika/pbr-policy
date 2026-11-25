#!/usr/bin/env python3
"""
★★★ 关键核验：那个 N=387 是真实数据还是拼接假象？

═══ 为什么要查 ═══
塌陷轨迹显示：t=100 时 age=1 的 N = 387，而预热期 N(t,0) ≈ 23。
一步之差，迭代数涨 16 倍。这决定了后续所有判断：

  若 387 是真实的物理瞬变  ⇒ 在线策略是被真实数据打败的（策略问题）
  若 387 是表格拼接的假象  ⇒ 是数据/口径问题（可以修）

同时核验：塌陷是否只在 linear 插值下出现。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

SPEC = {
    "fine": [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
             ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])],
    "x3":   [("x3", "x3run", [1,2,3,5,8], [1,2]),
             ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])],
}


def files_of(tag):
    out = []
    for prefix, logdir, Ks, rounds in SPEC[tag]:
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if os.path.exists(c) and os.path.exists(l):
                    out.append((prefix, K, R, c, l))
    return out


print("=" * 128)
print("★★★ A. N=387 溯源：哪些文件贡献了 (t≈100, age=1) 这个格子的值？")
print("=" * 128)
for tag in ("fine",):
    print("\n  ── %s ──" % tag)
    print("  %-40s %7s %7s %10s %10s %8s"
          % ("文件", "该步", "reusedFrom", "age", "N(该步)", "K"))
    for prefix, K, R, c, l in files_of(tag):
        try:
            rr = P.rows(c)
            seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            Ns = P.per_step_N(l)
        except Exception:
            continue
        if K == 1:
            # K=1 的 N(t,0) 基线
            if len(Ns) > 102:
                print("  %-40s %7d %7s %10s %10.1f %8d"
                      % (os.path.basename(c), 101, "-", "0", Ns[100], K))
            continue
        # 找 t=99..103 里 age>=1 的步
        for i in range(95, min(106, len(steps))):
            x = steps[i]; t = i+1
            rf = int(x["reusedFrom"])
            if rf >= 0:
                age = t - rf
                if age <= 2:
                    print("  %-40s %7d %10d %10d %10.1f %8d"
                          % (os.path.basename(c), t, rf, age, Ns[i], K))

print()
print("=" * 128)
print("★★★ B. 重建表格：K=1 基线附近的 N(t,0)，看 23→387 是否也出现在 age=0")
print("=" * 128)
for tag in ("fine", "x3"):
    print("\n  ── %s ──" % tag)
    for prefix, K, R, c, l in files_of(tag):
        if K != 1: continue
        Ns = P.per_step_N(l)
        if len(Ns) < 110: continue
        seg = Ns[95:110]
        print("  %-30s t=96..110 的 N(t,0): %s" % (os.path.basename(c),
              " ".join("%.0f" % v for v in seg)))
        print("  %-30s 中位=%.1f  这一段的均值=%.1f  全序列中位=%.1f"
              % ("", st.median(seg), sum(seg)/len(seg), st.median(Ns)))
        break

print()
print("=" * 128)
print("★★★ C. 塌陷是否只在 linear 插值下出现？")
print("=" * 128)


def build(tag, age_cap=None):
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag]:
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                try:
                    rr = P.rows(c)
                    seen = {}
                    for x in rr:
                        if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                            seen[int(x["timeIndex"])] = x
                    steps = [seen[t] for t in sorted(seen)]
                    Ns = P.per_step_N(l)
                    n = min(len(steps), len(Ns))
                    ent = []
                    for i in range(n):
                        x = steps[i]; rf = int(x["reusedFrom"])
                        ent.append((i+1, 0 if rf < 0 else i+1-rf, Ns[i]))
                    rv = [x["tPCSetup"]/x["tIter"] for x in rr
                          if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0]
                    rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                    nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                    files.append(dict(ent=ent, rv=rv,
                                      fac=(nrs/len(rbs)) if rbs else 1.0, nstep=len(steps)))
                except Exception:
                    pass
    Tmax = max(f["nstep"] for f in files)
    cells = defaultdict(list); rv = []; fac = []
    for d in files:
        for (t, a, N) in d["ent"]:
            if t > Tmax: break
            if age_cap is not None and a > age_cap: continue
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=Tmax)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)
print("  %-6s %6s %-8s %12s %12s %10s %12s" %
      ("配置", "cap", "插值", "oracle", "K=1", "在线", "在线/K1"))
for tag in ("fine", "x3"):
    for cap in (7, 12, 29):
        cfg = build(tag, age_cap=cap)
        if cfg is None: continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        for ip in ("linear", "step"):
            env = P.Env(cfg["tab"], mode="real", interp=ip)
            Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
            try:
                orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
            except AssertionError:
                print("  %-6s %6d %-8s  ★自检失败" % (tag, cap, ip)); continue
            onl = info["online"]; k1 = info["fixed"][1]
            print("  %-6s %6d %-8s %12.0f %12.0f %10.0f %11.2f%%"
                  % (tag, cap, ip, orc, k1, onl, 100*(onl/k1-1)))
    print()
print("=" * 128)
