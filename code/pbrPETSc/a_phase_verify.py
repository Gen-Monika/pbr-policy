#!/usr/bin/env python3
"""
★★★ 相位扫描多配置验收（A=6, K=7）

对每个配置检查：
  T1  种子格子 (B0, 1) 是否实测到（此前是空洞）
  T2  用相位扫描表跑模型在线，重建数是否复现 C++（有 C++ 参照的配置）
  T3  与 K 扫描在重叠格子上的一致性（比值中位应≈1.0）
  T4  年龄覆盖密度提升
  T5  主结果重算（oracle / K* / 在线）

C++ 实测参照只有 l20（a2smoke3 / a2A）与 fl30（a2B）。
其余配置无 C++ 在线数据，只能查 T1/T3/T4/T5。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"

# 配置 → (levels, K扫描的 (prefix, logdir, Ks, rounds), 基准步数, B0)
CFG = {
    "fx":   (10, [("fx", "fixed", [1,2,3,5,8], [1,2,3,4,5]),
                  ("covscan_l10", "covscan_l10", [13,20,30], [1,2,3])], 344, 100),
    "l15":  (15, [("l15", "l15", [1,2,3,5,8], [1,2,3,4,5]),
                  ("cov2_l15", "cov2_l15", [13,20,30], [1,2,3])], 344, 100),
    "l20":  (20, [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
                  ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])], 344, 100),
    "fine": (20, [("fine", "finerun", [1,2,3,5,8], [1,2,3]),
                  ("cov2_fine", "cov2_fine", [13,20,30], [1,2,3])], 720, 100),
    "x3":   (20, [("x3", "x3run", [1,2,3,5,8], [1,2]),
                  ("cov2_x3", "cov2_x3", [13,20,30], [1,2,3])], 1231, 100),
    "fl30": (30, [("fl30", "fl30run", [1,3,5], [1,2]),
                  ("cov2_fl30", "cov2_fl30", [8,13,20,30], [1,2,3])], 720, 100),
    "sth":  (5,  [("sth", "stefan", [1,2,3,5,8,13], [1,2,3]),
                  ("cov2_sth", "cov2_sth", [20,30], [1,2,3])], 5866, 50),
}
ORDER = ("fx", "l15", "l20", "fine", "x3", "fl30", "sth")
A = 6
K = A + 1
TAG = "phs"


def load_files(items, policy_B, base_n):
    """items = [(csv_path, log_path), ...] → (cells, rv, fac, nstep)"""
    cells = defaultdict(list); rv = []; fac = []; ns = 0
    for c, l in items:
        if not (os.path.exists(c) and os.path.exists(l)): continue
        try:
            rr = P.rows(c); seen = {}
            for x in rr:
                if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                    seen[int(x["timeIndex"])] = x
            steps = [seen[t] for t in sorted(seen)]
            if policy_B and len(steps) < base_n: continue
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
            ns = max(ns, len(steps))
        except Exception:
            pass
    if not cells: return None
    return dict(cells=cells, r=st.median(rv) if rv else float("nan"),
                s=st.median(fac) if fac else 1.0, nstep=ns)


def phase_files(tag, B0):
    pfx = tag
    out = []
    for B in range(B0 - A, B0 + 1):
        c = os.path.join(P2, "%s_%s_B%d_K%d_r1.csv" % (TAG, pfx, B, K))
        l = os.path.join(P2, "%s_%s" % (TAG, tag), "log.B%dK%d_r1" % (B, K))
        out.append((c, l))
    return out


def kscan_files(parts):
    out = []
    for pfx, logdir, Ks, rounds in parts:
        for k in Ks:
            for R in rounds:
                out.append((os.path.join(P2, "%s_pc_k%d_r%d.csv" % (pfx, k, R)),
                            os.path.join(P2, logdir, "log.r%dk%d" % (R, k))))
    return out


def sim_instr(env, r0, T, B0):
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
            if age in know and know[age]:
                delta = st.median(know[age])
            elif know:
                ks = sorted(kk for kk in know if know[kk])
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
            levels.append(N); a = 1; held = t; rbs.append(t); act = "R"
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1; act = "u"
        trace.append(dict(t=t, act=act, age=age, N=N))
    return tot, rbs, trace


def cpp_online(path):
    if not os.path.exists(path): return None
    rows = []
    with open(path, errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                rows.append((int(float(q[idx["timeIndex"]])),
                             int(float(q[idx["rebuild"]]))))
            except (ValueError, KeyError): pass
    return rows


CAND = (1,2,3,4,5,6,8,10,13,20,30,50)

print("=" * 130)
print("★★★ 相位扫描验收（A=%d, K=%d, 7 配置）" % (A, K))
print("=" * 130)

summary = []
for tag in ORDER:
    lvl, parts, base_n, B0 = CFG[tag]
    T = base_n
    print("\n" + "#" * 130)
    print("#  [%s]  levels=%d  T=%d  B0=%d" % (tag, lvl, T, B0))
    print("#" * 130)

    ph = load_files(phase_files(tag, B0), False, base_n)
    ks = load_files(kscan_files(parts), True, base_n)
    if ph is None:
        print("  ★ 相位扫描数据缺失"); continue

    nfile = sum(1 for c, l in phase_files(tag, B0) if os.path.exists(c))
    print("  相位扫描: 文件=%d/%d  格子=%d  r=%.2f  s=%.2f"
          % (nfile, A+1, len(ph["cells"]), ph["r"], ph["s"]))

    # ---- T1 种子格子 ----
    seed = (B0, 1)
    v = st.median(ph["cells"][seed]) if ph["cells"].get(seed) else None
    vk = st.median(ks["cells"][seed]) if (ks and ks["cells"].get(seed)) else None
    print("\n  T1 种子格子 (t=%d, a=1):" % B0)
    print("     相位扫描 = %s" % (("%.1f" % v) if v is not None else "★仍缺失"))
    print("     K 扫描   = %s" % (("%.1f" % vk) if vk is not None else "★不在（空洞）"))

    # ---- T3 重叠一致性 ----
    if ks:
        ov = set(ph["cells"]) & set(ks["cells"])
        if ov:
            ratios = []
            for k in ov:
                a1 = st.median(ph["cells"][k]); b1 = st.median(ks["cells"][k])
                if b1 > 1e-9: ratios.append(a1/b1)
            print("\n  T3 与 K 扫描重叠: 格子=%d  比值中位=%.3f  范围=[%.3f, %.3f]"
                  % (len(ov), st.median(ratios), min(ratios), max(ratios)))

    # ---- T4 覆盖密度 ----
    byt_ph = defaultdict(set); byt_ks = defaultdict(set)
    for (t_, a_) in ph["cells"]:
        if a_ > 0: byt_ph[t_].add(a_)
    if ks:
        for (t_, a_) in ks["cells"]:
            if a_ > 0: byt_ks[t_].add(a_)
    dens_ph = [len(byt_ph[t_]) for t_ in byt_ph]
    dens_ks = [len(byt_ks[t_]) for t_ in byt_ks]
    print("\n  T4 每 t 的可用年龄数: 相位=%.1f(中位)  K扫描=%.1f(中位)"
          % ((st.median(dens_ph) if dens_ph else 0),
             (st.median(dens_ks) if dens_ks else 0)))

    # ---- T2 与 C++ 对照（仅 l20 / fl30）----
    env = P.Env({k: st.median(vv) for k, vv in ph["cells"].items()},
                mode="real", interp="shape")
    tot, rbs, tr = sim_instr(env, ph["r"], T, B0)
    post = [t for t in rbs if t > B0]
    gaps = [post[i+1]-post[i] for i in range(len(post)-1)] if len(post) > 1 else []
    print("\n  T2 模型在线（相位扫描表, r0=1×r=%.1f）:" % ph["r"])
    print("     重建=%d  预热后=%d  间隔中位=%s"
          % (len(rbs), len(post), ("%.0f" % st.median(gaps)) if gaps else "-"))

    cppmap = {"l20": ["a2smoke3_onl_ONLs_r1.csv", "a2A_onl_ONLs_r1.csv"],
              "fl30": ["a2B_onl_ONLs_r1.csv"]}
    for fn in cppmap.get(tag, []):
        cr = cpp_online(os.path.join(P2, fn))
        if not cr: continue
        crb = [t for t, r_ in cr if r_ == 1]
        cpost = [t for t in crb if t > B0]
        cgaps = [cpost[i+1]-cpost[i] for i in range(len(cpost)-1)] if len(cpost) > 1 else []
        byt = {x["t"]: x for x in tr}
        ag = dis = 0
        for (t_, r_) in cr:
            if t_ <= B0 or t_ not in byt: continue
            if (byt[t_]["act"] == "R") == (r_ == 1): ag += 1
            else: dis += 1
        print("     ★ C++ %-26s 重建=%-4d 预热后=%-4d 间隔中位=%-4s 一致率=%.1f%%"
              % (os.path.basename(fn), len(crb), len(cpost),
                 ("%.0f" % st.median(cgaps)) if cgaps else "-",
                 100.0*ag/max(1, ag+dis)))

    # ---- T5 主结果 ----
    Ks = tuple(k for k in CAND if k <= env.amax_data + 1)
    try:
        orc, info = P.selfcheck(env, ph["r"], T, label=tag, Ks=Ks)
        kb = info["Kbest"]
        kk = 100*(info["fixed"][kb]/orc-1); onl = 100*(info["online"]/orc-1)
        print("\n  T5 主结果: oracle=%.0f  K*=%d(%.2f%%)  在线=%.2f%%  在线−K*=%+.2f pp"
              % (orc, kb, kk, onl, onl-kk))
        summary.append((tag, ph["r"], kb, kk, onl, onl-kk))
    except AssertionError as e:
        print("\n  T5 ★自检失败: %s" % str(e)[:80])

print("\n" + "=" * 130)
print("★★★ 汇总（相位扫描实测表）")
print("=" * 130)
print("  %-6s %8s %6s %11s %11s %11s" % ("配置", "r", "K*", "K*regret", "在线", "在线−K*"))
for (tag, r_, kb, kk, onl, gap) in summary:
    print("  %-6s %8.1f %6d %10.2f%% %10.2f%% %+10.2f pp" % (tag, r_, kb, kk, onl, gap))
if summary:
    g = [x[5] for x in summary]
    print("\n  在线 − K*：中位 %+.2f pp  范围 [%+.2f, %+.2f]  优于K*的配置数 %d/%d"
          % (st.median(g), min(g), max(g), sum(1 for x in g if x < 0), len(g)))
print("=" * 130)
