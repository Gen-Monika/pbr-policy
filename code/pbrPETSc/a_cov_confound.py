#!/usr/bin/env python3
"""
★★★ 排除混淆：regret 的跳变是"在线变差"还是"oracle 变强"？

═══ 为什么必须查 ═══
Q3 的 age_cap 实验同时改变了两个东西：
  (1) 在线策略看到的数据表（可用年龄变多）
  (2) oracle 的可行动作集（AMAX = amax_data + 1 随之变大）
oracle 的可行动作变多 ⇒ oracle 成本只会更低 ⇒ regret 的分母变小
⇒ 即使在线成本【完全不变】，regret 也会自动上升。

所以必须看【绝对成本】，不能只看 regret。

判据：
  若 orc 基本不变而 onl 暴涨  ⇒ 在线真的变差了（真问题）
  若 onl 基本不变而 orc 下降  ⇒ 是 oracle 的度量口径问题（假警报）
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
    "fx":   (344,  [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
                    ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])]),
    "l15":  (344,  [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
                    ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])]),
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


def build(tag, age_cap=None, k_cap=None, policy="A"):
    base_n = SPEC[tag][0]
    files = []
    for prefix, logdir, Ks, rounds in SPEC[tag][1]:
        for K in Ks:
            if k_cap and K > k_cap: continue
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
            if age_cap is not None and a > age_cap: continue
            cells[(t, a)].append(N)
        rv += d["rv"]; fac.append(d["fac"])
    if not cells: return None
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac), nsteps=Tmax)


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 128)
print("★★★ 混淆排查：绝对成本（不是 regret）随年龄覆盖上限的变化")
print("=" * 128)
print("  若 onl 随 cap 暴涨 ⇒ 在线真的变差；若只在 orc 下降 ⇒ 是度量口径。")
print()

for tag in ("fine", "x3", "fx", "l15"):
    print("  ── %s ──" % tag)
    print("  %-8s %8s %14s %14s %14s %10s %10s"
          % ("age≤", "amax", "oracle", "K=1", "在线", "在线/orc", "在线/K1"))
    for cap in (3, 5, 7, 10, 12, 14, 16, 19, 22, 25, 29):
        cfg = build(tag, age_cap=cap)
        if cfg is None: continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        env = P.Env(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        if not Ks: continue
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError:
            print("  %-8d %8d  ★自检失败" % (cap, env.amax_data)); continue
        onl = info["online"]; k1 = info["fixed"][1]
        print("  %-8d %8d %14.0f %14.0f %14.0f %9.2f%% %9.2f%%"
              % (cap, env.amax_data, orc, k1, onl, 100*(onl/orc-1), 100*(onl/k1-1)))
    print()

print("=" * 128)
print("★★★ 拆解：在线成本在哪一段暴涨？")
print("=" * 128)
print("  把 T 分成 8 段，看每段的【在线每步成本】与【最优固定周期每步成本】。")
print()
for tag in ("fine", "x3"):
    for cap in (7, 12, 29):
        cfg = build(tag, age_cap=cap)
        if cfg is None: continue
        T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]
        env = P.Env(cfg["tab"], mode="real", interp="linear")
        Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
        try:
            orc, info = P.selfcheck(env, r0, T, label=tag, Ks=Ks)
        except AssertionError:
            continue
        kb = info["Kbest"]
        # 重跑在线，记录轨迹
        know = defaultdict(list); levels = []
        steps = []
        tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
        for t in range(1, T+1):
            if t < P.B0 or held < 0 or not levels:
                rebuild = True
            else:
                age = t - held
                avg = acc/accn if accn else tot/max(1, t-1)
                lvl = levels[-1]
                if age in know and know[age]: delta = st.median(know[age])
                elif know:
                    ks = sorted(k for k in know if know[k])
                    if len(ks) >= 2:
                        a2, a1 = ks[-1], ks[-2]
                        d2, d1 = st.median(know[a2]), st.median(know[a1])
                        delta = d2 + (d2-d1)/max(1e-9, a2-a1)*(age-a2)
                    else: delta = st.median(know[ks[-1]])
                else: delta = 0.0
                rebuild = (lvl + max(0.0, delta)) > avg
            if rebuild:
                N = env(t, 0); c = r0 + N; tot += c
                acc, accn = (0.0, 0) if t < P.B0 else (c, 1)
                levels.append(N); a = 1; held = t
                steps.append((t, "R", N, env.amax_data))
            else:
                N = env(t, a); tot += N; acc += N; accn += 1
                if levels:
                    bm = st.median(levels)
                    if bm > 1e-9: know[a].append(N - bm)
                a += 1
                steps.append((t, "u", N, a-1))

        seg = T // 8
        print("  [%s] age≤%d  T=%d  在线总成本=%.0f (每步 %.1f)  K*=%d (每步 %.1f)"
              % (tag, cap, T, tot, tot/T, kb, info["fixed"][kb]/T))
        for s in range(8):
            lo, hi = s*seg+1, min((s+1)*seg, T)
            if hi < lo: continue
            sub = [x for x in steps if lo <= x[0] <= hi]
            o = sum(x[2] for x in sub) / len(sub)
            rs = [x for x in sub if x[1] == "R"]
            maxage = max(x[3] for x in sub)
            print("        段%d t=%4d-%4d  在线每步=%9.1f  重建%3d次  最大age=%2d"
                  % (s+1, lo, hi, o, len(rs), maxage))
        print()
print("=" * 128)
