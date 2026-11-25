#!/usr/bin/env python3
"""
★★★ Stage D：启发式阈值规则在真实非平稳算例上的表现

═══ 为什么这一组对照最能检验主贡献 ═══
导师的主贡献表述是「**不依赖过强老化假设**」。
四条既有阈值规则【全部预设固定维度或缓慢变化】——
它们是"依赖那些假设"的方法的具体形态。因此在真实非平稳算例上
测它们的损失，就是把该主张从断言变成实测。

═══ 能忠实实现的只有两条 ═══
| 规则 | 判定 | 依据 |
|---|---|---|
| Chalmers `max(2k₀,10)` | ✓ | k₀ = 刚重建后的迭代数，定义完整 |
| Code_Aster `REAC_PRECOND` | ✓ | "在 reac 次迭代内收敛则保持，超出则重分解" |
| Orellana `m/5` | ✗ | 需内点法的 m + 对角跳变检验 δ<1.5e5（CFD 场景无对应物） |
| Jorti `η_alg/η_sp` | ✗ | 需 GMRES 内的代数误差估计量 η_alg（我们没有） |

不可实现本身也是证据：它们绑在特定求解器结构上。

═══ 环境模型（与 A1c/A1d 一致，保证可比） ═══
N(t, a) = 在时间步 t、预条件子年龄为 a 时的该步迭代数。
从已有 K 扫描数据取 (t, age) 的跨轮中位 —— 与在线策略用的是同一张表。

★ 为什么这是【保守】的假设：所有阈值策略都按"能准确知道 N(t,a)"评估，
  真实在线策略还需从观测中估计它。所以给了阈值策略一个它实际没有的优势。
"""
import os, re, sys, statistics as st
from collections import defaultdict

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
CSV_HDR = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
           "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
           "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def per_step_N(p):
    out, cur = [], []
    for ln in open(p, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur)); cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out


def rows(path):
    o = []
    for ln in open(path):
        q = ln.rstrip("\n").split(",")
        if len(q) != 25: continue
        try:
            d = dict(zip(CSV_HDR, q))
            for k in d:
                if k not in ("field", "kind"): d[k] = float(d[k])
            o.append(d)
        except ValueError: pass
    return o


def build(tag, logdir, rounds, Ks, costmode="step"):
    cells = defaultdict(list); rv = []; fac = []; ns = None
    for K in Ks:
        for R in rounds:
            c = "%s_pc_k%d_r%d.csv" % (tag, K, R)
            l = os.path.join(logdir, "log.r%dk%d" % (R, K))
            if not (os.path.exists(c) and os.path.exists(l)): continue
            rr = rows(c); seen = {}
            for d in rr:
                if int(d["rep"]) >= 0 and int(d["timeIndex"]) not in seen:
                    seen[int(d["timeIndex"])] = d
            rr = [seen[t] for t in sorted(seen)]
            Ns = per_step_N(l); n = min(len(rr), len(Ns))
            if ns is None or n > ns: ns = n
            for i in range(n):
                d = rr[i]; t = i + 1
                rf = int(d["reusedFrom"])
                cells[(t, 0 if rf < 0 else t-rf)].append(Ns[i])
            allr = rows(c)
            for d in allr:
                if int(d["reused"]) == 0 and d["tPCSetup"] > 1e-4 and d["tIter"] > 0:
                    rv.append(d["tPCSetup"]/d["tIter"])
            rbs = set(int(d["timeIndex"]) for d in allr if int(d["reused"]) == 0)
            nrs = sum(1 for d in allr if int(d["reused"]) == 0)
            if rbs: fac.append(nrs/len(rbs))
    if not cells: return None
    f = st.median(fac) if fac else 1.0
    r1 = st.median(rv) if rv else float("nan")
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r=r1*(f if costmode == "step" else 1.0), r1=r1, fac=f, nsteps=ns)


def mk(tab):
    """
    ★★ 修复版环境（2026-10-12）：超范围必须【外推增长】，绝不回退到小年龄。

    旧版用 min(ages, key=|a-aa|) 取"最近年龄"。当 a 超出该步覆盖范围时
    （实测表只覆盖 age ≤ 4–7，而 DP 会扫到 60），最近年龄可能是一个很小的值，
    于是 DP 以为"复用 60 步"只花 age≈0 的迭代数 ⇒ oracle 低于物理下界
    （l20 曾算出 139/步，而 K=1 是 285/步，下界不可能低于 K=1 的一半）。
    该 bug 使 A1b/A1c/A1d 与 Stage D 首轮的全部 regret 数字作废。
    """
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v
    sa = {t: sorted(d) for t, d in byt.items()}

    bya = defaultdict(list)
    for (t, a), v in tab.items(): bya[a].append(v)
    curve = {a: st.median(v) for a, v in bya.items()}
    amx = max(curve)

    ks = sorted(curve)
    if len(ks) >= 2:
        gsl = (curve[ks[-1]] - curve[ks[-2]])/max(1e-9, ks[-1] - ks[-2])
    else:
        gsl = 1.0
    gsl = max(1e-6, gsl)

    def N(t, a):
        row = byt.get(t)
        if row is None:
            if a in curve: return curve[a]
            return curve[amx] + gsl*(a - amx)
        if a in row: return row[a]
        ages = sa[t]
        if a > ages[-1]:
            if len(ages) >= 2:
                sl = (row[ages[-1]] - row[ages[-2]])/max(1e-9, ages[-1] - ages[-2])
            else:
                sl = gsl
            return row[ages[-1]] + max(sl, gsl)*(a - ages[-1])
        lo = [x for x in ages if x <= a]
        return row[lo[-1]] if lo else row[ages[0]]
    return N, curve


# ═══════════════════════════ 策略 ═══════════════════════════

def sim_fixed(Nfn, r0, K, T, b0=100):
    """每 K 步重建（基线 C）"""
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < b0 or (t-b0) % K == 0:
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


def sim_dp(Nfn, r0, T, b0=100, AMAX=25):
    """oracle（DP 上界）"""
    INF = float("inf")
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            best = r0 + Nfn(t, 0) + V[t+1][1]
            if t > b0 and a+1 <= AMAX:
                best = min(best, Nfn(t, a) + V[t+1][a+1])
            V[t][a] = best
    return V[1][1]


def sim_chalmers(Nfn, r0, T, b0=100, factor=2.0, floor=10.0):
    """
    ★ Chalmers: 迭代数超过 max(factor·k₀, floor) 时重建。
      k₀ = 最近一次重建后那一步的迭代数（新分解基线）。
      —— 这是【绝对阈值】型规则：阈值锚在 k₀ 上，与漂移无关。
    """
    tot = 0.0; a = 0; k0 = None; nrb = 0
    for t in range(1, T+1):
        N = Nfn(t, 0 if a == 0 else a)
        rebuild = False
        if t < b0:
            rebuild = True
        elif a == 0:
            rebuild = True
        else:
            thr = max(factor*(k0 if k0 else N), floor)
            if N > thr:
                rebuild = True
        if rebuild:
            k0 = Nfn(t, 0)
            tot += r0 + Nfn(t, 0); a = 1; nrb += 1
        else:
            tot += N; a += 1
    return tot, nrb


def sim_reac(Nfn, r0, T, b0=100, reac=5.0):
    """
    ★ Code_Aster REAC_PRECOND: 预条件子在"GCPC 于 reac 次迭代内收敛"期间保持，
      超出则重分解。⇒ 同样是【绝对迭代数阈值】。
      文档明言只在多次连续求解上才划算，且利用"相邻迭代的相对接近"。
    """
    tot = 0.0; a = 0; nrb = 0
    for t in range(1, T+1):
        if t < b0 or a == 0:
            rebuild = True
        else:
            rebuild = Nfn(t, a) > reac
        if rebuild:
            tot += r0 + Nfn(t, 0); a = 1; nrb += 1
        else:
            tot += Nfn(t, a); a += 1
    return tot, nrb


def sim_ratio(Nfn, r0, T, b0=100, frac=0.20):
    """
    ★ "回收文献的 20%/50% 规则"：迭代数相对基线上涨超过 frac 就重建。
      这是【相对阈值】型，比上面两条更宽容（会跟随漂移）。
    """
    tot = 0.0; a = 0; k0 = None; nrb = 0
    for t in range(1, T+1):
        N = Nfn(t, 0 if a == 0 else a)
        if t < b0 or a == 0:
            rebuild = True
        else:
            base = k0 if k0 else N
            rebuild = N > base*(1.0 + frac)
        if rebuild:
            k0 = Nfn(t, 0)
            tot += r0 + Nfn(t, 0); a = 1; nrb += 1
        else:
            tot += N; a += 1
    return tot, nrb


def sim_online_rs(Nfn, r0, T, b0=100):
    """本文在线策略（P0 变体；与 A1c 的 sim_online 同逻辑）"""
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    for t in range(1, T+1):
        if t < b0 or held < 0 or not levels:
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
            N = Nfn(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < b0 else (c, 1)
            levels.append(N); a = 1; held = t
        else:
            N = Nfn(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
    return tot


CONFIGS = [
    ("fx",   "fixed",   [1,2,3,4,5],       [1,2,3,5,8],        3),
    ("l15",  "l15",     [1,2,3,4,5],       [1,2,3,5,8],        3),
    ("l20",  "l20",     [1,2,3,4,5],       [1,2,3,5,8],        3),
    ("fine", "finerun", [1,2,3],           [1,2,3,5,8],        3),
    ("fl30", "fl30run", [1,2],             [1,3,5],            3),
    ("x3",   "x3run",   [1,2],             [1,2,3,5,8],        3),
    ("sth",  "stefan",  list(range(1,11)), [1,2,3,5,8,13],     4),
]

print("=" * 118)
print("★★★ Stage D：启发式阈值规则 vs 固定周期 vs 本文在线策略（同一条 N(t,a) 环境）")
print("=" * 118)
print("""
说明：所有策略在同一张 N(t,a) 表上评估（各配置自己的实测曲线）。
      代价口径：重建一步 = r + N(t,0)，复用一步 = N(t,a)，r 按每步分解次数计。
""")

summary = []
for tag, logdir, rounds, Ks, s in CONFIGS:
    cfg = build(tag, logdir, rounds, Ks)
    if cfg is None:
        print("[%s] 数据缺失，跳过" % tag); continue
    Nfn, curve = mk(cfg["tab"])
    T, r0 = cfg["nsteps"], cfg["r"]

    orc = sim_dp(Nfn, r0, T)
    row = dict(tag=tag, T=T, r=r0, s=s, fac=cfg["fac"])

    # ★ 自检 1：oracle 必须 ≤ 任何固定周期策略
    _fxall = {K: sim_fixed(Nfn, r0, K, T) for K in (1,2,3,4,5,8,13,20)}
    _kbest = min(_fxall, key=_fxall.get)
    assert orc <= _fxall[_kbest] + 1e-6, \
        "自检失败：oracle(%.0f) > 最优固定周期 K=%d(%.0f)" % (orc, _kbest, _fxall[_kbest])
    # ★ 自检 2：oracle 不得低于"每步只付最小可能迭代数"的绝对下界
    _lb = sum(min(Nfn(t, 0), Nfn(t, 25)) for t in range(1, T+1))
    assert orc >= _lb - 1e-6, \
        "自检失败：oracle(%.0f) < 绝对下界(%.0f)" % (orc, _lb)

    # --- 固定周期：全扫，取最优 ---
    fx = {}
    for K in (1, 2, 3, 4, 5, 8, 13, 20):
        fx[K] = sim_fixed(Nfn, r0, K, T)
    Kbest = min(fx, key=fx.get)
    row["Kbest"] = Kbest
    row["fix"] = 100*(fx[Kbest]/orc - 1)
    row["K1"] = 100*(fx[1]/orc - 1)
    row["orc"] = orc; row["c_fix"] = fx[Kbest]; row["c_K1"] = fx[1]

    # --- 启发式阈值 ---
    ch, ch_nrb = sim_chalmers(Nfn, r0, T)
    rc, rc_nrb = sim_reac(Nfn, r0, T, reac=max(1.0, 0.5*r0))
    r20, r20_nrb = sim_ratio(Nfn, r0, T, frac=0.20)
    r50, r50_nrb = sim_ratio(Nfn, r0, T, frac=0.50)
    row["chalmers"] = 100*(ch/orc - 1); row["ch_nrb"] = ch_nrb; row["c_ch"] = ch
    row["reac"] = 100*(rc/orc - 1);     row["rc_nrb"] = rc_nrb; row["c_rc"] = rc
    row["r20"] = 100*(r20/orc - 1);     row["r20_nrb"] = r20_nrb; row["c_r20"] = r20
    row["r50"] = 100*(r50/orc - 1);     row["r50_nrb"] = r50_nrb; row["c_r50"] = r50

    # --- 本文在线 ---
    onl = sim_online_rs(Nfn, r0, T)
    row["online"] = 100*(onl/orc - 1); row["c_onl"] = onl

    print("\n[%s]  T=%d  r=%.1f  s=%d  每步分解=%.2f  r_eff=%.1f"
          % (tag, T, cfg["r1"], s, cfg["fac"], r0))
    print("   %-34s %10s %10s %10s" % ("策略", "相对oracle", "重建次数", "vs最优K"))
    print("   %-34s %9.2f%% %10s %9.2f%%" %
          ("oracle (DP 上界)", 0.0, "-", row["fix"] - row["online"]))
    print("   %-34s %9s %10s %9s" %
          ("  [绝对成本/步]", "%.1f" % (orc/T), "-", "-"))
    print("   %-34s %9.2f%% %10d %9.2f%%" %
          ("固定 K=1（每步重建）", row["K1"], T, row["K1"]-row["fix"]))
    print("   %-34s %9.2f%% %10s %9.2f%%" %
          ("固定 K*=%d（事后最优）" % Kbest, row["fix"], "-", 0.0))
    print("   %-34s %9.2f%% %10d %+9.2f%%" %
          ("Chalmers max(2k0,10)", row["chalmers"], ch_nrb,
           row["chalmers"]-row["fix"]))
    print("   %-34s %9.2f%% %10d %+9.2f%%" %
          ("Code_Aster REAC_PRECOND", row["reac"], rc_nrb, row["reac"]-row["fix"]))
    print("   %-34s %9.2f%% %10d %+9.2f%%" %
          ("相对阈值 20%", row["r20"], r20_nrb, row["r20"]-row["fix"]))
    print("   %-34s %9.2f%% %10d %+9.2f%%" %
          ("相对阈值 50%", row["r50"], r50_nrb, row["r50"]-row["fix"]))
    print("   %-34s %9.2f%% %10s %+9.2f%%" %
          ("★ 本文在线策略", row["online"], "-", row["online"]-row["fix"]))
    summary.append(row)

print("\n" + "=" * 118)
print("★★★ Stage D 汇总（regret 相对各自 oracle，%%）")
print("=" * 118)
print("  （regret 相对【各自 oracle】；oracle 已修，且通过两条自检）")
print("  %-7s %8s %8s %10s %10s %10s %10s %10s %10s" %
      ("配置","T","r","K=1","最优K*","Chalmers","REAC","20%","在线"))
for d in summary:
    print("  %-7s %8d %8.1f %9.2f%% %9.2f%% %9.2f%% %9.2f%% %9.2f%% %9.2f%%"
          % (d["tag"], d["T"], d["r"], d["K1"], d["fix"], d["chalmers"],
             d["reac"], d["r20"], d["online"]))

print("\n  ★ 关键对照：各启发式阈值相对【最优固定周期】的额外损失（pp，>0 表示更差）")
print("  %-7s %12s %12s %12s %12s" % ("配置","Chalmers","REAC","20%","本文在线"))
for d in summary:
    print("  %-7s %+11.2f %+11.2f %+11.2f %+11.2f"
          % (d["tag"], d["chalmers"]-d["fix"], d["reac"]-d["fix"],
             d["r20"]-d["fix"], d["online"]-d["fix"]))

n_ch = sum(1 for d in summary if d["online"] < d["chalmers"])
n_rc = sum(1 for d in summary if d["online"] < d["reac"])
n_r20 = sum(1 for d in summary if d["online"] < d["r20"])
N = len(summary)
print()
print("  ⇒ 在线优于 Chalmers 的配置数: %d/%d" % (n_ch, N))
print("  ⇒ 在线优于 REAC_PRECOND 的配置数: %d/%d" % (n_rc, N))
print("  ⇒ 在线优于 20%% 相对阈值的配置数: %d/%d" % (n_r20, N))
