#!/usr/bin/env python3
"""定位 no-extrap 变体自检失败的具体断言"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
SPEC = {
    "fl30": (720,  [("fl30", "fl30run", [1,3,5], [1,2]),
                    ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])]),
    "sth":  (5866, [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
                    ("cov2_sth", "cov2_sth", [20,30], [1,2,3])]),
}


class EnvNoExtrap(P.Env):
    def __call__(self, t, a):
        if self.mode == "frozen":
            return super().__call__(t, a)
        d = self.byt.get(t)
        if d is None:
            return self.curve.get(a, self.curve[self.amax_data])
        ages = self.sa[t]
        if a in d: return d[a]
        if self.interp == "step":
            lo = [x for x in ages if x <= a]
            return d[lo[-1]] if lo else d[ages[0]]
        if a <= ages[0]:  return d[ages[0]]
        if a >= ages[-1]: return d[ages[-1]]
        lo = max(x for x in ages if x <= a)
        hi = min(x for x in ages if x >= a)
        if hi == lo: return d[lo]
        w = (a - lo)/(hi - lo)
        return (1-w)*d[lo] + w*d[hi]


def build(tag):
    base_n = SPEC[tag][0]
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                try:
                    rr = P.rows(c); seen = {}
                    for x in rr:
                        if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                            seen[int(x["timeIndex"])] = x
                    steps = [seen[t] for t in sorted(seen)]
                    Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
                    ent = [(i+1, 0 if int(steps[i]["reusedFrom"]) < 0
                            else i+1-int(steps[i]["reusedFrom"]), Ns[i]) for i in range(n)]
                    rv = [x["tPCSetup"]/x["tIter"] for x in rr
                          if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0]
                    rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                    nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                    files.append(dict(ent=ent, rv=rv, fac=(nrs/len(rbs)) if rbs else 1.0,
                                      nstep=len(steps)))
                except Exception:
                    pass
    files = [f for f in files if f["nstep"] >= base_n]
    Tmax = max(f["nstep"] for f in files)
    cells = defaultdict(list); rv = []; fac = []
    for d in files:
        for (t, a, N) in d["ent"]:
            if t > Tmax: break
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=Tmax)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)
for tag in ("fl30", "sth"):
    cfg = build(tag)
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    print("=" * 110)
    print("[%s]  T=%d  r_eff=%.1f" % (tag, T, r0))
    print("=" * 110)
    for nm, cls in (("原版(外推)", P.Env), ("修正(不外推)", EnvNoExtrap)):
        env = cls(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        AMAX = env.amax_for(T)
        orc = P.sim_dp(env, r0, T, AMAX)
        fx = {K: P.sim_fixed(env, r0, K, T) for K in Ks}
        kb = min(fx, key=fx.get)
        onl = P.sim_online(env, r0, T)
        once = []
        for tstar in (P.B0, P.B0 + (T-P.B0)//4, P.B0 + (T-P.B0)//2, P.B0 + 3*(T-P.B0)//4):
            c = sum(r0 + env(t, 0) for t in range(1, tstar+1))
            c += sum(env(t, t-tstar) for t in range(tstar+1, T+1))
            once.append(c)
        cm = min(once)
        print("  [%s]  amax_data=%d AMAX=%d" % (nm, env.amax_data, AMAX))
        print("     oracle      = %14.0f  (每步 %.1f)" % (orc, orc/T))
        print("     最优固定 K=%-3d = %14.0f  (每步 %.1f)   %s"
              % (kb, fx[kb], fx[kb]/T,
                 "OK" if orc <= fx[kb] + 1e-6 else "★ oracle > K* 违反断言"))
        print("     在线        = %14.0f  (每步 %.1f)   %s"
              % (onl, onl/T, "OK" if orc <= onl + 1e-6 else "★ oracle > 在线 违反断言"))
        print("     建一次用到底 = %14.0f  (每步 %.1f)   %s"
              % (cm, cm/T, "OK" if orc <= cm + 1e-6 else "★ oracle > 单次 违反断言"))
        print("     env(t=200, a=1/5/20/60) = %.1f / %.1f / %.1f / %.1f"
              % (env(200, 1), env(200, 5), env(200, 20), env(200, 60)))
        print()
