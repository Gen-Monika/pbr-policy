#!/usr/bin/env python3
"""
★★★ 方向 5 判别实验：决策瓶颈是 r 还是漂移？

═══ 判别逻辑 ═══
对每个真实配置，构造一个【与它同 r、同 N₀、但人为平稳】的对照序列，
然后比较各类策略在两者上的 regret：

  若 regret(真实) ≈ regret(平稳)       ⇒ 漂移不重要，瓶颈是 r
  若 regret(真实) ≫ regret(平稳)       ⇒ 漂移重要，自适应有价值

═══ 关键：如何构造"平稳"对照而不引入其他差异 ═══
两条独立路径，互相印证：

【A】打乱相位（phase scramble）
   把 N(t,a) 表的 t 维随机置换 —— 漂移的时间结构被打乱，
   但 (a→N) 的边际分布、N₀、r 全部不变。
   ⇒ 这是最干净的"只去漂移、不动其他"的操作。

【B】冻结劣化（frozen decay）
   令 N(t,a) = N(t,0)，即"因子永不劣化"。
   ⇒ 决策空间归零，用来确认实验装置能分辨"有决策空间"与"无决策空间"。

═══ 报告什么 ═══
对每种（策略 × 数据集）组合给出 regret，并做 5 轮相位打乱的重复。

★ 注意：本实验只回答"漂移结构是否影响 regret"，
  不回答"漂移是否影响收益"（那是 A2 的实机结论：收益 −28%~−47%）。
"""
import os, re, random, statistics as st
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


def build(tag, logdir, rounds, Ks):
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
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


def make_env(tab, rng=None, mode="real"):
    """
    mode:
      real    —— 原表（真实漂移）
      scramble—— 把 (t→行) 的映射随机置换（去漂移，保留边际分布）
      frozen  —— N(t,a) := N(t,0)（无劣化，决策空间归零）
    """
    byt = defaultdict(dict)
    for (t, a), v in tab.items(): byt[t][a] = v

    Tmax = max(byt)
    other = [t for t in range(1, Tmax+1) if t not in byt or not byt[t]]
    real_t = sorted(t for t in byt if byt[t])

    if mode == "scramble" and rng is not None:
        perm = real_t[:]
        rng.shuffle(perm)
        newbyt = {}
        for src, dst in zip(real_t, perm):
            newbyt[dst] = dict(byt[src])
        byt = newbyt

    sa = {t: sorted(d) for t, d in byt.items()}

    bya = defaultdict(list)
    for t, d in byt.items():
        for a, v in d.items(): bya[a].append(v)
    GLOBAL_MAXAGE = max(bya)
    curve = {a: st.median(v) for a, v in bya.items()}
    ks = sorted(curve)
    amx = ks[-1]
    gsl = (curve[ks[-1]] - curve[ks[-2]])/max(1e-9, ks[-1]-ks[-2]) if len(ks) >= 2 else 1.0
    gsl = max(1e-6, gsl)

    def N(t, a):
        d = byt.get(t)
        if not d:
            # 该步无数据（打乱后可能出现空洞）：用全局曲线兜底
            return curve[a] if a in curve else curve[amx] + gsl*(a-amx)
        if mode == "frozen":
            # 无劣化：任何年龄都用该步的新因子值
            return d.get(0, curve[0])
        if a in d: return d[a]
        ages = sa[t]
        if a > ages[-1]:
            sl = ((d[ages[-1]] - d[ages[-2]])/max(1e-9, ages[-1]-ages[-2])) if len(ages) >= 2 else gsl
            return d[ages[-1]] + max(sl, gsl)*(a - ages[-1])
        lo = [x for x in ages if x <= a]
        return d[lo[-1]] if lo else d[ages[0]]
    return N, curve, GLOBAL_MAXAGE


def sim_dp(Nfn, r0, T, b0=100, AMAX=None):
    """
    ★★ 修复版 DP（2026-10-12，第二次修正）。

    三个必须同时正确的点：
      (1) AMAX 必须覆盖实测数据支持的最大年龄。
          若 AMAX 小于它，DP 会【被迫】每 AMAX 步重建一次
          （因为 a+1 > AMAX 时只剩重建分支）⇒ oracle 被人为抬高。
          实测：各配置的实测最大 age 是 4–12，与 max(K) 配套，
          故取 AMAX = 实测最大 age 即可（超出即重建，正对应
          "我们有数据支持的最大周期"）。
      (2) 不能靠外推去估大年龄（表只覆盖 age≤12，而"永不重建"需要 age 到 244；
          线性外推会给出天价 ⇒ DP 误以为长复用不可能 ⇒ oracle 再次偏高）。
      (3) 入口是 V[1][0]（第 1 步开始前尚未建），不是 V[1][1]。
    """
    INF = float("inf")
    if AMAX is None:
        AMAX = 26
    V = [[INF]*(AMAX+1) for _ in range(T+2)]
    for a in range(AMAX+1): V[T+1][a] = 0.0
    for t in range(T, 0, -1):
        for a in range(AMAX+1):
            if t <= b0 or a >= AMAX:
                V[t][a] = r0 + Nfn(t, 0) + V[t+1][1]     # 强制重建
                continue
            V[t][a] = min(r0 + Nfn(t, 0) + V[t+1][1],
                          Nfn(t, a) + V[t+1][a+1])
    return V[1][0]


def sim_fixed(Nfn, r0, K, T, b0=100):
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < b0 or (t-b0) % K == 0:
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


def sim_best_fixed(Nfn, r0, T, b0=100):
    best = (1e18, None)
    for K in (1, 2, 3, 4, 5, 6, 8, 10, 13, 20, 30, 50):
        v = sim_fixed(Nfn, r0, K, T, b0)
        if v < best[0]: best = (v, K)
    return best


def sim_online(Nfn, r0, T, b0=100):
    """本文在线策略（P0），与 A1c / C++ 移植一致"""
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


def sim_reac(Nfn, r0, T, reac, b0=100):
    tot = 0.0; a = 0
    for t in range(1, T+1):
        if t < b0 or a == 0: rebuild = True
        else: rebuild = Nfn(t, a) > reac
        if rebuild:
            tot += r0 + Nfn(t, 0); a = 1
        else:
            tot += Nfn(t, a); a += 1
    return tot


CONFIGS = [
    ("fx",   "fixed",   [1,2,3,4,5],       [1,2,3,5,8]),
    ("l15",  "l15",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("l20",  "l20",     [1,2,3,4,5],       [1,2,3,5,8]),
    ("fine", "finerun", [1,2,3],           [1,2,3,5,8]),
    ("fl30", "fl30run", [1,2],             [1,3,5]),
    ("x3",   "x3run",   [1,2],             [1,2,3,5,8]),
    ("sth",  "stefan",  list(range(1,11)), [1,2,3,5,8,13]),
]
NREP = 5
print("=" * 118)
print("★★★ 方向 5：决策瓶颈是 r 还是漂移？（相位打乱判别实验）")
print("=" * 118)
print("""
三个数据集（同一配置的同一份数据）：
  real     真实序列（有漂移的时间结构）
  scramble 把 t 维随机置换（去漂移，保留 r、N₀、边际分布） —— 5 轮
  frozen   令 N(t,a)=N(t,0)（无劣化，决策空间归零）—— 装置对照

策略：最优固定周期 K*、本文在线、REAC@120
报告：regret 相对各数据集自己的 oracle
""")

print("  %-6s %8s %9s %10s %11s %10s %11s %9s" %
      ("配置","r_eff","数据集","oracle/步","最优K*","在线","REAC@120","漂移增益"))
summary = []
for tag, logdir, rounds, Ks in CONFIGS:
    cfg = build(tag, logdir, rounds, Ks)
    if cfg is None: continue
    tab = cfg["tab"]; T = cfg["nsteps"]; r0 = cfg["r1"]*cfg["fac"]

    # ---------- real ----------
    Nfn, _, AM = make_env(tab, mode="real")
    orc = sim_dp(Nfn, r0, T, AMAX=AM)
    kf, kb = sim_best_fixed(Nfn, r0, T)
    onl = sim_online(Nfn, r0, T)
    rc = sim_reac(Nfn, r0, T, 120)
    real = dict(orc=orc, K=kb, fix=100*(kf/orc-1),
                onl=100*(onl/orc-1), reac=100*(rc/orc-1))
    print("  %-6s %8.1f %9s %10.1f %10s %9.2f%% %9.2f%% %9s"
          % (tag, r0, "real", orc/T, "K=%d" % kb, real["onl"], real["reac"], "-"))

    # ---------- scramble ----------
    sc_onl, sc_reac, sc_fix, sc_orc = [], [], [], []
    for rep in range(NREP):
        rng = random.Random(1000+rep)
        Ng, _, AMg = make_env(tab, rng=rng, mode="scramble")
        o = sim_dp(Ng, r0, T, AMAX=AMg)
        sc_orc.append(o)
        kk, _ = sim_best_fixed(Ng, r0, T)
        sc_fix.append(100*(kk/o - 1))
        sc_onl.append(100*(sim_online(Ng, r0, T)/o - 1))
        sc_reac.append(100*(sim_reac(Ng, r0, T, 120)/o - 1))
    print("  %-6s %8s %9s %10.1f %10s %9.2f%% %9.2f%% %9s"
          % ("", "", "scramble", st.median(sc_orc)/T, "—",
             st.median(sc_onl), st.median(sc_reac), "—"))

    # ---------- frozen ----------
    Nz, _, AMz = make_env(tab, mode="frozen")
    # ★ frozen 下环境对所有年龄都有定义（N(t,a):=N(t,0)），
    #   故 AMAX 取"永不重建"所需的完整范围，而不是数据表的覆盖范围。
    #   否则 DP 会被迫每 AMAX 步重建，oracle 虚高、在线 regret 变负（已踩过）。
    oz = sim_dp(Nz, r0, T, AMAX=T-100)
    kz, kzb = sim_best_fixed(Nz, r0, T)
    zz_onl = 100*(sim_online(Nz, r0, T)/oz - 1)
    zz_reac = 100*(sim_reac(Nz, r0, T, 120)/oz - 1)
    print("  %-6s %8s %9s %10.1f %10s %9.2f%% %9.2f%% %9s"
          % ("", "", "frozen", oz/T, "K=%d" % kzb, zz_onl, zz_reac, "—"))

    # ★ 装置自检：oracle 必须 ≤ 永不复用 与 最优固定周期
    _warm = sum(r0 + Nfn(t, 0) for t in range(1, 101))
    _post = sum(Nfn(t, 0) for t in range(101, T+1))
    _noreuse = _warm + _post
    _ok1 = orc <= _noreuse + 1e-6
    _ok2 = orc <= kf + 1e-6
    _ok3 = orc <= onl + 1e-6
    if True:
        _zw = sum(r0 + Nz(t, 0) for t in range(1, 101)) + sum(Nz(t, 0) for t in range(101, T+1))
        _zok = oz <= _zw + 1e-6
        print("  %-6s %8s %9s %10s %10s %9s %9s  [frozen 自检 %s]"
              % ("", "", "", "", "", "", "",
                 ("✓ oz=%.0f ≤ 永不复用=%.0f" % (oz, _zw)) if _zok
                 else ("✗ oz=%.0f > 永不复用=%.0f" % (oz, _zw))))
    print("  %-6s %8s %9s %10s %10s %9s %9s  [自检 %s%s%s]"
          % ("", "", "", "", "", "", "",
             "✓" if _ok1 else "✗永不复用", "✓" if _ok2 else "✗最优K",
             "✓" if _ok3 else "✗在线"))

    summary.append(dict(tag=tag, r=r0, T=T,
                        real_onl=real["onl"], sc_onl=st.median(sc_onl),
                        real_reac=real["reac"], sc_reac=st.median(sc_reac),
                        frozen_onl=zz_onl, frozen_reac=zz_reac,
                        real_orc=orc/T, sc_orc=st.median(sc_orc)/T,
                        frozen_orc=oz/T,
                        sc_onl_all=sc_onl))

print("\n" + "=" * 118)
print("★★★ 判别汇总：在线策略的 regret（%）在三种数据集上的对比")
print("=" * 118)
print("  %-6s %10s %12s %12s %14s %12s" %
      ("配置","real","scramble","frozen","漂移增益(real-scr)","判定"))
gain = []
for d in summary:
    g = d["real_onl"] - d["sc_onl"]
    gain.append(g)
    verdict = "漂移重要" if g > 3.0 else ("漂移无关" if abs(g) < 1.5 else "弱")
    print("  %-6s %9.2f%% %11.2f%% %11.2f%% %+13.2f pp %12s"
          % (d["tag"], d["real_onl"], d["sc_onl"], d["frozen_onl"], g, verdict))

print()
print("  ⇒ 漂移增益的中位 = %+.2f pp，范围 [%+.2f, %+.2f]"
      % (st.median(gain), min(gain), max(gain)))
print("  ⇒ 判定：%s" %
      ("漂移结构对 regret 有实质影响" if st.median(gain) > 3.0
       else "★ 漂移结构对 regret 几乎无影响 ⇒ 瓶颈是 r，不是漂移"))

print("\n  ★ 装置有效性核对（oracle/步 在 real vs frozen 上的对比）")
print("  %-6s %14s %14s %10s" % ("配置","real oracle/步","frozen oracle/步","比值"))
for d in summary:
    print("  %-6s %14.1f %14.1f %10.2f"
          % (d["tag"], d["real_orc"], d["frozen_orc"],
             d["frozen_orc"]/d["real_orc"]))
print("  ⇒ frozen 的 oracle/步 应【低于】real（无劣化 ⇒ 不用重建 ⇒ 每步更便宜）")
print("     若 frozen 的 oracle 反而更高，说明装置有问题，结论不可信。")
