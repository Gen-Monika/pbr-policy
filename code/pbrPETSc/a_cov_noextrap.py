#!/usr/bin/env python3
"""
★★★ 根因确认：N=387 是 pbrlib 线性外推的产物，不是真实数据

═══ 线索 ═══
所有原始文件在 (t=101, age=1) 处的实测值都是 46.0。
但塌陷轨迹里 env(100, 1) = 387.0。差 8.4 倍。

═══ 机理（待验证）═══
Env.__call__ 的 linear 分支：
    if a >= ages[-1]:
        if len(ages) >= 2: sl = (d[ages[-1]] - d[ages[-2]])/(ages[-1]-ages[-2])
        else:              sl = self.gslope          ← ★ 这里
        return d[ages[-1]] + max(sl, self.gslope)*(a - ages[-1])

而 gslope 是用【全局曲线】末端算的：
    self.gslope = (curve[maxAge] - curve[maxAge-1]) / (maxAge - maxAge-1)

覆盖到 age=29 时，curve 末端的斜率极大（199→...→ 几千），
于是【任何】t 处只要本地只有一个年龄（t<100 时只有 age=0），
请求 age=1 就会拿到  N(t,0) + 巨大的 gslope = 23 + 364 = 387。

⇒ 这是与"陷阱 28（最近邻回退）"同类的【边界外推】bug，
  但方向相反：上次是"回退到小年龄导致低估"，这次是"外推斜率过大导致高估"。

═══ 本脚本核验 ═══
1. 直接打印 Env 内部状态，复现 387
2. 逐项拆解 gslope 的构成
3. 证明：把 linear 分支的"超范围"行为改成"取末端值"（不外推），
   塌陷立即消失
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


print("=" * 128)
print("★★★ 1. 直接复现：Env 在 (t=100, a=1) 返回什么")
print("=" * 128)
for tag in ("fine",):
    for cap in (7, 12, 29):
        cfg = build(tag, age_cap=cap)
        env = P.Env(cfg["tab"], mode="real", interp="linear")
        print("\n  [%s] cap=%d  amax_data=%d" % (tag, cap, env.amax_data))
        print("    全局曲线 curve（按年龄）:")
        for a in sorted(env.curve):
            print("      age=%-3d curve=%10.1f" % (a, env.curve[a]))
        print("    gslope = %.3f   ← 全局末端斜率" % env.gslope)
        print("    byt[100] 可用年龄 = %s" % sorted(env.byt.get(100, {})))
        print("    N(100,0) = %.1f" % env(100, 0))
        v1 = env(100, 1)
        print("    env(100, 1) = %.1f   ← 应为 46（实测），实得 %.1f" % (v1, v1))
        print("    env(100, 2) = %.1f" % env(100, 2))
        print("    env(100, 5) = %.1f" % env(100, 5))

print()
print("=" * 128)
print("★★★ 2. 对照：把超范围外推改成为取末端值后，塌陷是否消失")
print("=" * 128)


class EnvNoExtrap(P.Env):
    """把 linear 的超范围行为从外推改成取末端值（不外推）。"""
    def __call__(self, t, a):
        if self.mode == "frozen":
            return super().__call__(t, a)
        d = self.byt.get(t)
        if d is None:
            if a in self.curve: return self.curve[a]
            return self.curve[self.amax_data]
        ages = self.sa[t]
        if a in d: return d[a]
        if self.interp == "step":
            lo = [x for x in ages if x <= a]
            return d[lo[-1]] if lo else d[ages[0]]
        # linear: 区间内插值，区间外【取末端值】—— 不再外推
        if a <= ages[0]:  return d[ages[0]]
        if a >= ages[-1]: return d[ages[-1]]
        lo = max(x for x in ages if x <= a)
        hi = min(x for x in ages if x >= a)
        if hi == lo: return d[lo]
        w = (a - lo)/(hi - lo)
        return (1-w)*d[lo] + w*d[hi]


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)
print("  %-6s %6s %-14s %12s %12s %12s %11s" %
      ("配置", "cap", "Env 变体", "oracle", "K=1", "在线", "在线/K1"))
for tag in ("fine", "x3"):
    for cap in (7, 12, 29):
        cfg = build(tag, age_cap=cap)
        if cfg is None: continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        for nm, cls in (("原版(会外推)", P.Env), ("不外推", EnvNoExtrap)):
            for ip in ("linear",):
                env = cls(cfg["tab"], mode="real", interp=ip)
                Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
                try:
                    orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
                except AssertionError as e:
                    print("  %-6s %6d %-14s  ★自检失败 %s" % (tag, cap, nm, str(e)[:40]))
                    continue
                onl = info["online"]; k1 = info["fixed"][1]
                print("  %-6s %6d %-14s %12.0f %12.0f %12.0f %10.2f%%"
                      % (tag, cap, nm, orc, k1, onl, 100*(onl/k1-1)))
    print()

print("=" * 128)
print("★★★ 3. 结论")
print("=" * 128)
print("  若 不外推 列的 在线/K1 在各 cap 下都稳定在 -48% 左右，")
print("  则塌陷（在线/K1 ≈ 0%）完全由 pbrlib 的超范围外推造成，")
print("  而不是在线策略本身的缺陷。")
print("=" * 128)
