#!/usr/bin/env python3
"""
★★★ 同算例严格对照：damBreak(=l20, levels=20) 上「模型」vs「C++ 实测」

═══ 待验证的假设 ═══
C++ 的 ONLs 用 PBR_PETSC_ONLINE_RCOST=solve，每次重建只计 1×r
（日志里的 rMed = 89.33）；而模型 sim_online 喂的是
r_eff = s·r = 2.99 × 90.79 = 271.6。两者差 3 倍。
重建代价的口径直接决定判据阈值：
    est = lvl + max(0,delta)  vs  avg
把 r0 从 271.6 降到 89.33，avg 会大幅下降（因为重建步的 acc = r0 + N），
于是同样的 est 就【更容易】超过 avg ⇒ 重建更频繁。

若把模型也改成 1×r 口径后能复现 221 次/间隔 2，则说明：
  · 模型与 C++ 之间【没有机制差异】，此前所有分歧都是 r0 口径造成的
  · l20 的"周期 2"不是缺陷，而是【重建代价被低估 3 倍】的必然结果
  · l15 模型层的"周期 2"另有原因（linear 插值外推，已确认）
    —— 两个相像的现象，两个不同的成因

═══ 对照项 ═══
  A. N(t,0)：模型 env(t,0) vs C++ 实测 prevN
  B. 重建次数 / 预热后重建 / 间隔中位 / 最大 age
  C. 逐步 est / avg 量级
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0

SPEC_L20 = [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
            ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])]
BASE_N_L20 = 344


# ─────────────────────── 数据加载 ───────────────────────
def load_l20(policy="B"):
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    nfile = 0
    for prefix, logdir, Ks, rounds in SPEC_L20:
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (prefix, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
                if policy == "B" and len(steps) < BASE_N_L20: continue
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
                ns = max(ns, len(steps)); nfile += 1
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns, nfile=nfile)


# ─────────────────────── C++ 日志解析 ───────────────────────
def read_online(path):
    rows = []
    with open(path, errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                rows.append(dict(
                    t=int(float(q[idx["timeIndex"]])),
                    rb=int(float(q[idx["rebuild"]])),
                    age=int(float(q[idx["runAge"]])),
                    est=float(q[idx["est"]]),
                    avg=float(q[idx["avg"]]),
                    rMed=float(q[idx["rMed"]]),
                    pN=float(q[idx["prevN"]]),
                    pFact=float(q[idx["prevFact"]]),
                    dm=(q[idx["dm"]] if "dm" in idx else "?")))
            except (ValueError, KeyError):
                pass
    return rows


def cpp_extract(path):
    """返回 (N_by_t, rb_by_t, rows)。N_by_t[t] 由下一步的 prevN 反推。"""
    rows = read_online(path)
    N, rb = {}, {}
    for i, r in enumerate(rows):
        rb[r["t"]] = r["rb"]
        if i > 0 and r["pN"] > 0:
            N[rows[i-1]["t"]] = r["pN"]
    return N, rb, rows


def stats_from_rb(rb_list, T):
    post = [t for t in rb_list if t > B0]
    gaps = [post[i+1]-post[i] for i in range(len(post)-1)]
    return dict(total=len(rb_list), post=len(post),
                med=(st.median(gaps) if gaps else None),
                gaps=gaps)


# ─────────────────────── 模型：在线策略（instrumented）───────────────────────
def sim_instr(env, r0, T, lvl_mode="last"):
    """与 pbrlib.sim_online 逐行等价，额外返回重建时刻与逐步轨迹。"""
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    rbs = []; trace = []
    for t in range(1, T+1):
        age = -1; lvl = float("nan"); delta = float("nan"); avg = float("nan")
        if t < B0 or held < 0 or not levels:
            rebuild = True
        else:
            age = t - held
            avg = acc/accn if accn else tot/max(1, t-1)
            lvl = levels[-1]
            if lvl_mode == "trend" and len(levels) >= 2:
                lvl = levels[-1] + (levels[-1] - levels[-2])
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
            N = env(t, 0); c = r0 + N; tot += c
            acc, accn = (0.0, 0) if t < B0 else (c, 1)
            levels.append(N); a = 1; held = t; rbs.append(t)
            act = "R"
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1
            act = "u"
        trace.append(dict(t=t, act=act, age=age, N=N, lvl=lvl,
                          delta=delta, avg=avg))
    return tot, rbs, trace, know, levels


# ═══════════════════════════════════════════════════════════════
print("=" * 126)
print("★★★ 0. 前提核对：damBreak_petsc 与 l20 是否同一算例")
print("=" * 126)
cfg = load_l20()
T = cfg["nsteps"]
r_single = cfg["r1"]; s = cfg["fac"]; r_eff = r_single * s
print("  l20 K 扫描：文件数=%d  T=%d" % (cfg["nfile"], T))
print("  实测 r（单次分解，tPCSetup/tIter 中位） = %.2f" % r_single)
print("  实测 s（每步分解次数）                  = %.2f" % s)
print("  ⇒ r_eff = s·r = %.1f" % r_eff)
print()
print("  A2 的 a2A_pc_*.csv 头部：levels=20 nCells=2268 nFaces=4432")
print("  l20_pc_k1_r1.csv 头部  ：levels=%s nCells=%s nFaces=%s"
      % (P.rows(os.path.join(P2, "l20_pc_k1_r1.csv"))[0]["levels"],
         P.rows(os.path.join(P2, "l20_pc_k1_r1.csv"))[0]["nCells"],
         P.rows(os.path.join(P2, "l20_pc_k1_r1.csv"))[0]["nFaces"]))

env_shape = P.Env(cfg["tab"], mode="real", interp="shape")
env_linear = P.Env(cfg["tab"], mode="real", interp="linear")

# ═══════════════════════════════════════════════════════════════
print()
print("=" * 126)
print("★★★ A. N(t,0)：模型 env(t,0) vs C++ 实测 prevN")
print("=" * 126)
CPP = {}
for nm, p in (("ONLs(新库)", "a2smoke3_onl_ONLs_r1.csv"),
              ("ONLp(旧库)", "a2A_onl_ONLp_r1.csv"),
              ("ONLs(旧库)", "a2A_onl_ONLs_r1.csv")):
    fp = os.path.join(P2, p)
    if os.path.exists(fp):
        N, rb, rows = cpp_extract(fp)
        CPP[nm] = (N, rb, rows)
        print("  已读 %-14s 步数=%d 重建=%d" % (nm, len(rows), sum(rb.values())))

if CPP:
    Nc, rbc, rowsc = CPP["ONLs(新库)"]
    print()
    print("  %-8s %14s %14s %10s" % ("t", "C++ 实测 N", "模型 env(t,0)", "比值"))
    for t in (1, 20, 50, 80, 99, 150, 200, 300, 344):
        if t in Nc:
            m = env_shape(t, 0)
            print("  %-8d %14.1f %14.1f %10.2f" % (t, Nc[t], m, Nc[t]/max(1e-9, m)))
    # 整体比较（只在重建步上，因为 C++ 的 prevN 只在重建步等于 N(t,0)）
    ratio = []
    for t, v in Nc.items():
        if rbc.get(t) == 1 and v > 0:
            ratio.append(v/max(1e-9, env_shape(t, 0)))
    if ratio:
        print("  预热期重建步上 比值(C++/模型): 中位=%.3f  均值=%.3f  样本=%d"
              % (st.median(ratio), sum(ratio)/len(ratio), len(ratio)))
        print("  ⇒ 接近 1.0 说明模型的 N(t,0) 与实测一致，两边喂的是同一份数据")

# ═══════════════════════════════════════════════════════════════
print()
print("=" * 126)
print("★★★ B. 核心对照：把模型的 r0 换成 C++ 的口径，能否复现重建次数")
print("=" * 126)
print("  C++ 实测：")
ref = {}
for nm, (N, rb, rows) in CPP.items():
    stt = stats_from_rb([t for t in rb if rb[t] == 1], T)
    ages = [r["age"] for r in rows if r["t"] > B0]
    rmed = [r["rMed"] for r in rows if r["rMed"] > 0]
    ref[nm] = stt
    print("    %-14s 重建=%-4d 预热后=%-4d 间隔中位=%-4s 最大age=%-4s rMed中位=%.2f"
          % (nm, stt["total"], stt["post"],
             ("%.0f" % stt["med"]) if stt["med"] else "-",
             max(ages) if ages else "-",
             st.median(rmed) if rmed else 0.0))
print()
print("  模型（sim_online，与 pbrlib 逐行等价）：")
print("    %-34s %8s %8s %8s %8s %10s"
      % ("口径", "r0", "重建", "预热后", "间隔中位", "最大age"))
MODEL = {}
for nm, r0v, ip in (("1×r   (对应 ONLs)", r_single, "shape"),
                    ("2×r",               2*r_single, "shape"),
                    ("3×r=s·r (对应 ONLp)", r_eff, "shape"),
                    ("1×r  [linear 插值]",  r_single, "linear"),
                    ("3×r   [linear 插值]", r_eff, "linear")):
    env = env_shape if ip == "shape" else env_linear
    tot, rbs, tr, know, levels = sim_instr(env, r0v, T)
    ref_tot = P.sim_online(env, r0v, T)
    assert abs(tot - ref_tot) < 1e-6, "instrumented 与 pbrlib 不等价！"
    stt = stats_from_rb(rbs, T)
    ages = [x["age"] for x in tr if x["t"] > B0 and x["age"] >= 0]
    MODEL[nm] = (stt, tot)
    print("    %-34s %8.1f %8d %8d %8s %8d"
          % (nm, r0v, stt["total"], stt["post"],
             ("%.0f" % stt["med"]) if stt["med"] else "-",
             max(ages) if ages else -1))

print()
print("  ── 判定 ──")
if "ONLs(新库)" in ref and "1×r   (对应 ONLs)" in MODEL:
    a = ref["ONLs(新库)"]["total"]; b = MODEL["1×r   (对应 ONLs)"][0]["total"]
    print("    C++ ONLs 重建=%d   模型(1×r) 重建=%d   差=%+d" % (a, b, b-a))
if "ONLp(旧库)" in ref and "3×r=s·r (对应 ONLp)" in MODEL:
    a = ref["ONLp(旧库)"]["total"]; b = MODEL["3×r=s·r (对应 ONLp)"][0]["total"]
    print("    C++ ONLp 重建=%d   模型(s·r)  重建=%d   差=%+d" % (a, b, b-a))

# ═══════════════════════════════════════════════════════════════
print()
print("=" * 126)
print("★★★ C. 逐步 est / avg 对照（验证机制，不只是计数）")
print("=" * 126)
if "ONLs(新库)" in CPP:
    Nc, rbc, rowsc = CPP["ONLs(新库)"]
    tm, rbs, tr, know, levels = sim_instr(env_shape, r_single, T)
    byt = {x["t"]: x for x in tr}
    print("  %-6s %22s %22s" % ("t", "C++ (est / avg)", "模型 (est / avg)"))
    shown = 0
    for r in rowsc:
        t = r["t"]
        if t <= B0 or t not in byt or shown >= 14: continue
        m = byt[t]
        m_est = m["lvl"] + max(0.0, m["delta"]) if m["delta"] == m["delta"] else float("nan")
        print("  %-6d %9.1f / %-10.1f %9.1f / %-10.1f  C++rb=%s 模型=%s"
              % (t, r["est"], r["avg"], m_est, m["avg"],
                 r["rb"], "R" if m["act"] == "R" else "u"))
        shown += 1
print("=" * 126)
