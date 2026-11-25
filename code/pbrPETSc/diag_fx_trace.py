#!/usr/bin/env python3
"""fx 的在线决策逐点追踪：为什么它停在 K≈2 而最优是 K=3？"""
import sys, statistics as st
sys.path.insert(0, ".")
import pbrlib as P

cfg = P.load_config("fx", "fixed", [1,2,3,4,5], [1,2,3,5,8])
T, r0 = cfg["nsteps"], cfg["r1"]*cfg["fac"]
env = P.Env(cfg["tab"], mode="real", interp="linear")

know = {}; levels = []
tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
print("fx: T=%d r_eff=%.1f  (重建一步付 r_eff + N(t,0))" % (T, r0))
print()
print("%-5s %-4s %-8s %-8s %-9s %-9s %-8s %s" %
      ("t", "age", "lvl", "delta", "est", "avg", "accn", "决策"))
for t in range(P.B0, P.B0+26):
    if held < 0 or not levels:
        rebuild = True; est = thr = None; age = 0
    else:
        age = t - held
        avg = acc/accn if accn else tot/max(1, t-1)
        lvl = levels[-1]
        d = know.get(age)
        if d: delta = st.median(d); src = "有样本"
        else:
            ks = sorted(k for k in know if know[k])
            if len(ks) >= 2:
                a2, a1 = ks[-1], ks[-2]
                d2, d1 = st.median(know[a2]), st.median(know[a1])
                delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2); src = "外推"
            elif ks:
                delta = st.median(know[ks[-1]]); src = "单点"
            else:
                delta = 0.0; src = "无"
        est = lvl + max(0.0, delta)
        rebuild = est > avg
        print("%-5d %-4d %-8.1f %-8.1f %-9.1f %-9.1f %-8d %s (%s)"
              % (t, age, lvl, delta, est, avg, accn,
                 "重建" if rebuild else "复用", src))
    if rebuild:
        N = env(t, 0); c = r0 + N; tot += c
        acc, accn = (c, 1)
        levels.append(N); a = 1; held = t
    else:
        N = env(t, a); tot += N; acc += N; accn += 1
        bm = st.median(levels)
        if bm > 1e-9: know.setdefault(a, []).append(N - bm)
        a += 1
