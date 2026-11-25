#!/usr/bin/env python3
"""
★★★ 验证"形状迁移"填充法（shape transfer）

═══ 思路 ═══
前两种填充方式都站不住：
  · 外推（现状）：用全局末端斜率填局部空洞 ⇒ env(100,1)=405，实测 46
  · clamp      ：大年龄免费 ⇒ "建一次用到底"比 oracle 便宜 ⇒ 自检崩

换一个角度：把 N(t,a) 分解成【水平】×【形状】
      N(t,a) = N(t,0) × G(a)
其中
  · N(t,0) 是【每步都测到】的稠密量（K=1 与各 K 的重建步都给）
  · G(a) = curve(a)/curve(0) 是【跨 t 汇总】的年龄增长因子（形状）

物理理由：预条件子老化导致的迭代数增长，主要取决于"老化了多少步"，
        而不是"在哪一步老化"。所以形状 G(a) 可跨 t 迁移，
        水平 N(t,0) 随 t 变化（非平稳）。

关键检验：预热期 t<100 时本地只有 age=0，形状迁移给出
      N(100,1) = N(100,0) × curve(1)/curve(0)
若这正好等于实测的 46，说明该方案在小年龄处是对的 —— 而小年龄正是
决定在线策略会不会塌陷的地方。
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
    "l15":  [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
             ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])],
    "fx":   [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])],
    "l20":  [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
             ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])],
    "fl30": [("fl30", "fl30run", [1,3,5], [1,2]),
             ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])],
    "sth":  [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
             ("cov2_sth", "cov2_sth", [20,30], [1,2,3])],
}


def load_raw(tag):
    """返回 (tab, rv, fac, nstep)，不做任何填充。"""
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    for prefix, logdir, Ks, rounds in SPEC[tag]:
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
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


# ═══════════════ 形状迁移 Env ═══════════════
class EnvShape(P.Env):
    """
    N(t,a) = N(t,0) × G(a)，其中 G(a)=curve(a)/curve(0)。

    · 本地有实测值时，优先用实测值（保持 t 依赖的真实细节）
    · 本地缺失时用形状迁移
    · 超出 amax_data 时，对形状做【线性延伸】（用末端斜率），
      保持单调递增 —— 避免"大年龄免费"导致的自检崩溃
    """
    def __init__(self, tab, mode="real", interp="shape", rng=None):
        super().__init__(tab, mode=mode, interp=interp, rng=rng)
        ks = sorted(self.curve)
        self._gmax = ks[-1]
        self._g0 = self.curve[ks[0]] if self.curve.get(0) else st.median(
            [v for k, v in self.curve.items()])
        if ks[-1] >= 2:
            self._gslope_shape = ((self.curve[ks[-1]] - self.curve[ks[-2]]) /
                                  max(1e-9, ks[-1]-ks[-2]))
        else:
            self._gslope_shape = 0.0

    def _G(self, a):
        """年龄增长因子 G(a) = N(t,a)/N(t,0)，跨 t 汇总。"""
        if a in self.curve:
            return self.curve[a]/self._g0
        ks = sorted(self.curve)
        if a < ks[0]:
            return self.curve[ks[0]]/self._g0
        # 超出：线性延伸
        ext = self.curve[ks[-1]] + self._gslope_shape*(a - ks[-1])
        return max(ext, self.curve[ks[-1]])/self._g0

    def __call__(self, t, a):
        if self.mode == "frozen":
            d = self.byt.get(t)
            return d.get(0, self.curve[0]) if d else self.curve[0]

        d = self.byt.get(t)
        if d and a in d:
            return d[a]                      # 优先实测

        # 水平：N(t,0)；缺失则退回全局中位
        if d and 0 in d:
            lvl = d[0]
        else:
            lvl = self.curve.get(0, 1.0)
        return max(1.0, lvl * self._G(a))


print("=" * 128)
print("★★★ 1. 关键检验：形状迁移能否复现小年龄的实测值？")
print("=" * 128)
for tag in ("fine",):
    cfg = load_raw(tag)
    env0 = P.Env(cfg["tab"], mode="real", interp="linear")
    envS = EnvShape(cfg["tab"])
    print("\n  [%s]  amax_data=%d" % (tag, env0.amax_data))
    ks = sorted(env0.curve)
    print("     curve(年龄→跨t中位): " + "  ".join(
        "a=%d:%.0f" % (a, env0.curve[a]) for a in ks[:10]))
    print("     G(a) = curve(a)/curve(0): " + "  ".join(
        "a=%d:%.2f" % (a, envS._G(a)) for a in ks[:10]))
    print("     curve(0)=%.1f   gslope_shape=%.1f" % (envS._g0, envS._gslope_shape))
    print()
    print("     %-14s %10s %10s %10s   %s" %
          ("(t, a)", "实测", "外推(旧)", "形状迁移", "判定"))
    for (t, a) in ((100, 1), (100, 2), (100, 5), (200, 1), (200, 5), (300, 3)):
        real = env0.byt.get(t, {}).get(a)
        real = ("%.1f" % real) if real is not None else "—"
        print("     %-14s %10s %10.1f %10.1f" %
              ("(%d,%d)" % (t, a), real, env0(t, a), envS(t, a)))
    # 找出 t 处有实测 a=1 的，比较形状迁移 vs 实测
    print()
    print("     系统性核对：所有【本地有 age=1 实测值】的 t，形状迁移的偏差")
    devs = []
    for t, dd in sorted(env0.byt.items()):
        if 1 in dd and 0 in dd and dd[0] > 1:
            pred = dd[0] * envS._G(1)
            devs.append(pred/dd[1])
    if devs:
        print("       样本数=%d  预测/实测 的比值: 中位=%.3f  均值=%.3f  范围=[%.3f, %.3f]"
              % (len(devs), st.median(devs), sum(devs)/len(devs),
                 min(devs), max(devs)))

print()
print("=" * 128)
print("★★★ 2. 三种填充 × 七配置：regret 与自检")
print("=" * 128)


class EnvClamp(P.Env):
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


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)
print("  %-6s %-16s %10s %8s %12s %11s %12s %11s %s"
      % ("配置", "填充方式", "amax", "AMAX", "oracle", "K*regret", "在线", "在线−K*", "自检"))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = load_raw(tag)
    if cfg is None:
        print("  %-6s ★数据缺失" % tag); continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    for nm, cls, kw in (("外推(现状)", P.Env, dict(interp="linear")),
                        ("clamp", EnvClamp, dict(interp="linear")),
                        ("形状迁移", EnvShape, dict())):
        env = cls(cfg["tab"], mode="real", **kw)
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: continue
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
            bad = "OK"
        except AssertionError as e:
            s = str(e)
            bad = "★" + ("oracle>在线" if "在线" in s else
                         "oracle>单次" if "建一次" in s else "其他")
            print("  %-6s %-16s %10d %8s %12s %11s %12s %11s %s"
                  % (tag, nm, env.amax_data, "—", "—", "—", "—", "—", bad))
            continue
        kb = info["Kbest"]
        kk = 100*(info["fixed"][kb]/orc-1); onl = 100*(info["online"]/orc-1)
        print("  %-6s %-16s %10d %8d %12.0f %10.2f%% %11.2f%% %+10.2f pp %s"
              % (tag, nm, env.amax_data, info["AMAX"], orc, kk, onl, onl - kk, bad))
    print()
print("=" * 128)
