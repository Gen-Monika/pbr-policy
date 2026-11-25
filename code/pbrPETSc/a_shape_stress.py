#!/usr/bin/env python3
"""
★★★ 形状迁移的稳健性：最偏年龄是否影响决策？

═══ 已知 ═══
留一验证的中位偏差都在 ±7% 内（无系统偏袒），但个别年龄偏差大：
  fl30 age=4  -37.5%      ← 而 fl30 的 K*=5，决策边界就在 age 4~5
  sth  age=1  -15.8%
  x3   age=13 -20.7%

若决策边界上的年龄被系统性低估，在线策略会【过度复用】，
而 oracle 也会因为同样的低估而给出偏低的成本 ⇒ regret 仍可能好看但都错。

═══ 本脚本做三件事 ═══
1. 对每个配置，找出偏差最大的年龄，看它与 K* 的距离
2. 用【保形扰动】做压力测试：把形状 G(a) 整体乘上 [1+ε] 或 [1-ε]，
   看 regret 与自检是否稳定（ε = ±20%，覆盖观测到的偏差幅度）
3. 给出结论：形状迁移是否可信到能用于论文
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

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


def load_raw(tag):
    cells = defaultdict(list); rv = []; fac = []; ns = 0
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
                    for i in range(n):
                        x = steps[i]; rf = int(x["reusedFrom"])
                        cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
                    for x in rr:
                        if int(x["reused"]) == 0 and x["tPCSetup"] > 1e-4 and x["tIter"] > 0:
                            rv.append(x["tPCSetup"]/x["tIter"])
                    rbs = set(int(x["timeIndex"]) for x in rr if int(x["reused"]) == 0)
                    nrs = sum(1 for x in rr if int(x["reused"]) == 0)
                    if rbs: fac.append(nrs/len(rbs))
                    ns = max(ns, n)
                except Exception:
                    pass
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


class EnvShape(P.Env):
    """形状迁移 + 可调扰动 eps（对 G(a) 整体缩放，用于压力测试）"""
    def __init__(self, tab, mode="real", interp="shape", rng=None, eps=0.0):
        super().__init__(tab, mode=mode, interp=interp, rng=rng)
        ks = sorted(self.curve)
        self._gmax = ks[-1]
        self._g0 = self.curve.get(0, st.median(list(self.curve.values())))
        self._eps = eps
        if ks[-1] >= 2:
            self._gsl = ((self.curve[ks[-1]] - self.curve[ks[-2]]) /
                         max(1e-9, ks[-1]-ks[-2]))
        else:
            self._gsl = 0.0

    def _G(self, a):
        if a in self.curve:
            base = self.curve[a]/self._g0
        else:
            ks = sorted(self.curve)
            if a < ks[0]:
                base = self.curve[ks[0]]/self._g0
            else:
                ext = self.curve[ks[-1]] + self._gsl*(a - ks[-1])
                base = max(ext, self.curve[ks[-1]])/self._g0
        # 扰动只作用于 a>=1，且随年龄放大（模拟"越老越不确定"）
        return base * (1.0 + self._eps*min(1.0, a/5.0))

    def __call__(self, t, a):
        if self.mode == "frozen":
            d = self.byt.get(t)
            return d.get(0, self.curve[0]) if d else self.curve[0]
        d = self.byt.get(t)
        if d and a in d:
            return d[a]
        lvl = d[0] if (d and 0 in d) else self.curve.get(0, 1.0)
        return max(1.0, lvl*self._G(a))


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 130)
print("★★★ 1. 最偏年龄与决策边界的距离")
print("=" * 130)
print("  %-6s %10s %14s %12s   %s" % ("配置", "K*", "最偏年龄", "偏差", "风险判断"))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load_raw(tag)
    if cfg is None: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    env = EnvShape(cfg["tab"])
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
    kb = info["Kbest"]
    # 重算偏差表
    byt = defaultdict(dict)
    for (t, a), v in cfg["tab"].items(): byt[t][a] = v
    bya = defaultdict(list)
    for t, d in byt.items():
        for a, v in d.items(): bya[a].append(v)
    curve_all = {a: st.median(v) for a, v in bya.items()}
    biases = []
    for a0 in sorted(curve_all):
        if a0 == 0 or len(bya.get(a0, [])) < 10: continue
        cwo = {a: v for a, v in curve_all.items() if a != a0}
        ks = sorted(cwo); g0 = cwo.get(0)
        if not g0: continue
        lo = [x for x in ks if x < a0]; hi = [x for x in ks if x > a0]
        if lo and hi:
            l_, h_ = lo[-1], hi[0]; w = (a0-l_)/(h_-l_)
            G = ((1-w)*cwo[l_] + w*cwo[h_])/g0
        elif lo: G = cwo[lo[-1]]/g0
        elif hi: G = cwo[hi[0]]/g0
        else: continue
        ratios = [d[0]*G/d[a0] for t, d in byt.items()
                  if a0 in d and 0 in d and d[0] > 1 and t > P.B0]
        if len(ratios) >= 5: biases.append((a0, st.median(ratios)-1.0))
    if not biases:
        print("  %-6s %10d %14s" % (tag, kb, "—")); continue
    worst_a, worst_b = min(biases, key=lambda z: z[1])
    dist = abs(worst_a - kb)
    risk = "★高风险：偏差年龄就在 K* 附近" if dist <= 2 else \
           ("中风险" if dist <= 5 else "低风险：远离 K*")
    print("  %-6s %10d %14d %11.1f%%   %s" % (tag, kb, worst_a, 100*worst_b, risk))

print()
print("=" * 130)
print("★★★ 2. 压力测试：把形状 G(a) 扰动 ε，看 regret 与自检的稳定性")
print("=" * 130)
print("  ε>0 = 高估老化劣化（偏袒重建）；ε<0 = 低估（偏袒复用）")
print()
EPS = (-0.30, -0.20, -0.10, 0.0, 0.10, 0.20, 0.30)
print("  %-6s %9s %8s" % ("配置", "K*", "自检") +
      "".join("%11s" % ("ε=%+.2f" % e) for e in EPS))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load_raw(tag)
    if cfg is None: continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    line = ""
    kb0 = None
    for e in EPS:
        env = EnvShape(cfg["tab"], eps=e)
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError:
            line += "%11s" % "★崩"; continue
        kb0 = info["Kbest"]
        line += "%10.2f%%" % (100*(info["online"]/orc-1))
    print("  %-6s %9s %8s%s" % (tag, kb0 if kb0 else "—", "OK", line))

print()
print("  （单元格 = 在线 regret vs oracle；★崩 = 自检失败）")
print()
print("  判据：若 |ε|≤0.20 时 regret 变化 <5 pp 且无崩溃 ⇒ 形状迁移稳健")
print("=" * 130)
