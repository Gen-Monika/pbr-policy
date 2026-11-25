#!/usr/bin/env python3
"""
★★★ 七配置 × 两种 Env 口径的完整对照

问题：pbrlib.Env 在 linear 模式下对【超出本地年龄范围】的点做外推，
      而外推斜率 gslope 取自【全局曲线末端】（覆盖到 age=29 时高达 383）。
      于是 t<100（本地只有 age=0）请求 age=1 时：
          env(100,1) = N(100,0) + 383 = 22 + 383 = 405
      而实测真值是 46。高估 8.8 倍。

后果：在线策略在 t=100 处看到一个巨大的 delta，判定"必须重建"，
      之后每步都重建 ⇒ 退化成 K=1 ⇒ regret 从 7.8% 跳到 106.7%。

本脚本回答：这个 bug 是否也污染了此前报告的主结果？
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


class EnvNoExtrap(P.Env):
    """超范围时不外推，取最近端点值。"""
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


CACHE = {}


def parse_one(prefix, logdir, K, R):
    key = (prefix, logdir, K, R)
    if key in CACHE: return CACHE[key]
    c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
    l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
    val = None
    if os.path.exists(c) and os.path.exists(l):
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
            val = dict(ent=ent, rv=rv, fac=(nrs/len(rbs)) if rbs else 1.0, nstep=len(steps))
        except Exception:
            val = None
    CACHE[key] = val
    return val


def build(tag, policy="B"):
    base_n = SPEC[tag][0]
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            for R in rounds:
                d = parse_one(prefix, logdir, K, R)
                if d: files.append(d)
    if policy == "B":
        files = [f for f in files if f["nstep"] >= base_n]
    if not files: return None
    Tmax = max(f["nstep"] for f in files)
    cells = defaultdict(list); rv = []; fac = []
    for d in files:
        for (t, a, N) in d["ent"]:
            if t > Tmax: break
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac), nsteps=Tmax)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 132)
print("★★★ 七配置 × 两种 Env 口径（政策 B：剔除截断文件）")
print("=" * 132)
print("  原版 = pbrlib.Env（超范围线性外推，gslope 取全局末端斜率）")
print("  修正 = 超范围取端点值（不外推）")
print()
print("  %-6s %-24s %10s %7s %12s %11s %12s %11s"
      % ("配置", "口径", "amax", "T", "oracle", "K*regret", "在线", "在线−K*"))
RES = {}
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    cfg = build(tag)
    if cfg is None:
        print("  %-6s ★数据缺失" % tag); continue
    T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
    for nm, cls in (("原版(外推)", P.Env), ("修正(不外推)", EnvNoExtrap)):
        env = cls(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError as e:
            print("  %-6s %-24s ★自检失败" % (tag, nm)); continue
        kb = info["Kbest"]
        kk = 100*(info["fixed"][kb]/orc-1); onl = 100*(info["online"]/orc-1)
        RES[(tag, nm)] = (onl, kk, kb, orc)
        print("  %-6s %-24s %10d %7d %12.0f %10.2f%% %11.2f%% %+10.2f pp"
              % (tag, nm, env.amax_data, T, orc, kk, onl, onl - kk))
    print()

print("=" * 132)
print("★★★ 口径变化带来的结论漂移")
print("=" * 132)
print("  %-6s %14s %14s %12s   %s" % ("配置", "原版 在线−K*", "修正 在线−K*", "漂移", "判定"))
for tag in ("fx", "l15", "l20", "fine", "x3", "fl30", "sth"):
    a = RES.get((tag, "原版(外推)")); b = RES.get((tag, "修正(不外推)"))
    if not a or not b:
        print("  %-6s %14s %14s" % (tag, "—", "—")); continue
    d = b[0] - a[0]
    flag = "★ 结论改变" if abs(d) > 5 else ("有漂移" if abs(d) > 1 else "稳定")
    print("  %-6s %+13.2f %+13.2f %+11.2f pp   %s" % (tag, a[0], b[0], d, flag))
print("=" * 132)
