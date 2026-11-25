#!/usr/bin/env python3
"""
★★★ decisive：在线策略为何在覆盖变大后退化为"每步重建"

═══ 已确认的事实 ═══
把年龄覆盖上限 cap 从 7 提到 12，fine 的在线 regret 从 7.84% 跳到 106.73%，
而且 在线/K=1 的比值是 0.01% —— 这意味着在线成本【精确等于】每步重建的成本。

逐段拆解显示：段2..段8 每段 90 步里有 90 次重建 —— 策略在【每一步】都重建。

所以这不是"估计器略差"，是策略退化成 K=1。必须找出触发点。

═══ 本脚本做三件事 ═══
1. 确认"在线 ≡ 每步重建"是精确等式（算术证据，不依赖模型）
2. 定位第一次塌陷的时刻，并打印那一刻的 know 表
3. 对照 cap=7（健康）与 cap=12（塌陷）的 know 表演化差异
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

SPEC = {
    "fine": (720,  [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
                    ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])]),
    "x3":   (1231, [("x3", "x3run", [1,2,3,5,8], [1,2]),
                    ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])]),
}

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


def build(tag, age_cap=None):
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            for R in rounds:
                d = parse_one(prefix, logdir, K, R)
                if d: files.append(d)
    if not files: return None
    Tmax = max(f["nstep"] for f in files)
    cells = defaultdict(list); rv = []; fac = []
    for d in files:
        for (t, a, N) in d["ent"]:
            if t > Tmax: break
            if age_cap is not None and a > age_cap: continue
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac), nsteps=Tmax)


def trace(env, r0, T):
    """完整重跑在线，逐步记录状态。返回轨迹列表。"""
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    tr = []
    for t in range(1, T+1):
        info = dict(t=t, action="R", age=0, N=0.0, lvl=float("nan"),
                    delta=float("nan"), avg=float("nan"), nknow=len(know))
        if t < P.B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            dsrc = "none"
            if age in know and know[age]:
                delta = st.median(know[age]); dsrc = "hit"
            elif know:
                ks = sorted(k for k in know if know[k])
                if len(ks) >= 2:
                    a2, a1 = ks[-1], ks[-2]
                    d2, d1 = st.median(know[a2]), st.median(know[a1])
                    delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                    dsrc = "extrap(%d,%d)" % (a1, a2)
                else:
                    delta = st.median(know[ks[-1]]); dsrc = "flat(%d)" % ks[-1]
            else:
                delta = 0.0; dsrc = "empty"
            rebuild = (lvl + max(0.0, delta)) > avg
            info.update(age=age, lvl=lvl, delta=delta, avg=avg, dsrc=dsrc)
        if rebuild:
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < P.B0 else (c, 1)
            levels.append(N); a = 1; held = t
            info.update(action="R", N=N)
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
            info.update(action="u", N=N)
        tr.append(info)
    return tot, tr, know, levels


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 126)
print("★★★ 1. 确认「在线 ≡ 每步重建」是精确等式")
print("=" * 126)
print("  %-6s %6s %16s %16s %14s %10s" %
      ("配置", "cap", "在线总成本", "K=1 总成本", "差", "相对差"))
for tag in ("fine", "x3"):
    for cap in (7, 12, 29):
        cfg = build(tag, age_cap=cap)
        if cfg is None: continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        env = P.Env(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        onl = info["online"]; k1 = info["fixed"][1]
        print("  %-6s %6d %16.0f %16.0f %14.0f %9.3f%%"
              % (tag, cap, onl, k1, onl - k1, 100*(onl/k1 - 1)))

print()
print("=" * 126)
print("★★★ 2. 定位塌陷时刻（fine, cap=12）")
print("=" * 126)
cfg = build("fine", age_cap=12)
T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
env = P.Env(cfg["tab"], mode="real", interp="linear")
tot, tr, know, levels = trace(env, r0, T)

# 找最后一段连续重建的起点
last_reuse = max((x["t"] for x in tr if x["action"] == "u" and x["t"] > P.B0), default=None)
print("  预热后最后一次【复用】发生在 t = %s" % last_reuse)
print("  ⇒ t > %s 的每一步都在重建（共 %d 步）"
      % (last_reuse, sum(1 for x in tr if x["t"] > (last_reuse or 0) and x["action"] == "R")))
print()
lo = max(P.B0, (last_reuse or P.B0) - 25)
print("  塌陷前后 40 步的决策细节：")
print("  %-6s %-4s %5s %10s %10s %10s %10s %-14s %s"
      % ("t", "动作", "age", "N(t,a)", "lvl", "delta", "avg", "delta来源", "est>avg?"))
for x in tr:
    if lo <= x["t"] <= lo + 40:
        mark = ""
        if x["action"] == "R" and x["t"] > P.B0 and not (x["delta"] != x["delta"]):
            est = x["lvl"] + max(0.0, x["delta"])
            mark = "%.1f %s %.1f → 重建" % (est, ">" if est > x["avg"] else "<=", x["avg"])
        print("  %-6d %-4s %5d %10.1f %10.1f %10.1f %10.1f %-14s %s"
              % (x["t"], x["action"], x["age"], x["N"], x["lvl"], x["delta"],
                 x["avg"], x.get("dsrc", ""), mark))

print()
print("  塌陷时刻的 know 表：")
for k in sorted(know):
    if know[k]:
        print("    age=%-4d n=%-5d median=%10.1f  min=%8.1f max=%8.1f"
              % (k, len(know[k]), st.median(know[k]), min(know[k]), max(know[k])))

print()
print("=" * 126)
print("★★★ 3. 对照：cap=7（健康）的 know 表")
print("=" * 126)
cfg7 = build("fine", age_cap=7)
env7 = P.Env(cfg7["tab"], mode="real", interp="linear")
tot7, tr7, know7, levels7 = trace(env7, cfg7["r1"]*cfg7["fac"], cfg7["nsteps"])
print("  在线总成本=%.0f  重建 %d 次（预热后 %d）"
      % (tot7, sum(1 for x in tr7 if x["action"] == "R"),
         sum(1 for x in tr7 if x["action"] == "R" and x["t"] > P.B0)))
for k in sorted(know7):
    if know7[k]:
        print("    age=%-4d n=%-5d median=%10.1f  min=%8.1f max=%8.1f"
              % (k, len(know7[k]), st.median(know7[k]), min(know7[k]), max(know7[k])))
print()
print("  对比 cap=12：在线总成本=%.0f  重建 %d 次（预热后 %d）"
      % (tot, sum(1 for x in tr if x["action"] == "R"),
         sum(1 for x in tr if x["action"] == "R" and x["t"] > P.B0)))
print("=" * 126)
