#!/usr/bin/env python3
"""
★★★ l15 的 C++ 在线验证：与模型逐决策对照

背景：l15 此前从未在 C++ 上跑过在线策略，结论全部来自模型。
模型（相位扫描实测表）预测 ONLs = 221 / 预热后 122 / 间隔 2 / iters=8040。

本脚本：
  1. 从 C++ 日志提取重建时刻，与模型逐决策比对（一致率）
  2. 与 l20 的历史实测并排（同一判据、不同 levels）
  3. 报告墙钟（同轮内交错，取中位）
  4. 检查实现缺陷的迹象：
     · 重建次数是否等于解析期望（无）
     · 迭代数在不同轮次间是否漂移（确定性检查）
     · ONLs 与 ONLp 是否如预期不同
     · 是否有 fatal / 步数不一致
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0


def read_online(path):
    rows = []
    if not os.path.exists(path): return rows
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
                    est=float(q[idx["est"]]), avg=float(q[idx["avg"]]),
                    rMed=float(q[idx["rMed"]]), pN=float(q[idx["prevN"]]),
                    dm=(q[idx["dm"]] if "dm" in idx else "?")))
            except (ValueError, KeyError): pass
    return rows


def load_phase_l15():
    """l15 的相位扫描表（A=6, K=7）"""
    A, K = 6, 7
    cells = defaultdict(list); rv = []
    for B in range(B0 - A, B0 + 1):
        c = os.path.join(P2, "phs_l15_B%d_K%d_r1.csv" % (B, K))
        l = os.path.join(P2, "phs_l15", "log.B%dK%d_r1" % (B, K))
        if not (os.path.exists(c) and os.path.exists(l)): continue
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
    return {k: st.median(v) for k, v in cells.items()}, st.median(rv)


def sim_instr(env, r0, T):
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
        trace.append(dict(t=t, act=act, age=age, N=N, lvl=lvl, delta=delta, avg=avg))
    return tot, rbs, trace


print("=" * 126)
print("★★★ l15 的 C++ 在线验证")
print("=" * 126)

# ---------- 1. C++ 各轮汇总 ----------
print("\n【C++ 实测 vs 模型预测】")
print("  %-42s %8s %8s %8s %8s" % ("文件", "重建", "预热后", "间隔中位", "最大age"))
CPP = {}
for mode in ("ONLs", "ONLp"):
    for R in (1, 2, 3):
        f = os.path.join(P2, "a2l15_onl_%s_r%d.csv" % (mode, R))
        rows = read_online(f)
        if not rows: continue
        rb = [r["t"] for r in rows if r["rb"] == 1]
        post = [t for t in rb if t > B0]
        gaps = [post[i+1]-post[i] for i in range(len(post)-1)] if len(post) > 1 else []
        ages = [r["age"] for r in rows if r["t"] > B0]
        CPP[(mode, R)] = rows
        print("  %-42s %8d %8d %8s %8d"
              % (os.path.basename(f), len(rb), len(post),
                 ("%.0f" % st.median(gaps)) if gaps else "-", max(ages) if ages else -1))

# ---------- 2. 模型预测 ----------
tab, r_single = load_phase_l15()
env = P.Env(tab, mode="real", interp="shape")
T = 344
tot, rbs_m, tr_m = sim_instr(env, r_single, T)
post_m = [t for t in rbs_m if t > B0]
gaps_m = [post_m[i+1]-post_m[i] for i in range(len(post_m)-1)] if len(post_m) > 1 else []
print("  %-42s %8d %8d %8s %8d"
      % ("★ 模型预测（相位扫描表, 1×r）", len(rbs_m), len(post_m),
         ("%.0f" % st.median(gaps_m)) if gaps_m else "-",
         max(x["age"] for x in tr_m if x["t"] > B0 and x["age"] >= 0)))

# ---------- 3. 逐决策一致率 ----------
print("\n【逐决策对照】")
print("  %-24s %10s %10s %10s" % ("C++ 文件", "一致", "不一致", "一致率"))
byt = {x["t"]: x for x in tr_m}
for (mode, R), rows in sorted(CPP.items()):
    ag = dis = 0; first = None
    for r in rows:
        t = r["t"]
        if t <= B0 or t not in byt: continue
        m = (byt[t]["act"] == "R"); c = (r["rb"] == 1)
        if m == c: ag += 1
        else:
            dis += 1
            if first is None: first = (t, c, m)
    tag = "a2l15_onl_%s_r%d" % (mode, R)
    extra = ""
    if first:
        extra = "  首个分歧 t=%d (C++=%s 模型=%s)" % (
            first[0], "重建" if first[1] else "复用", "重建" if first[2] else "复用")
    print("  %-24s %10d %10d %9.1f%%%s" % (tag, ag, dis, 100.0*ag/max(1, ag+dis), extra))

# ---------- 4. 确定性 / 实现缺陷检查 ----------
print("\n【实现缺陷检查】")
print("  1) 轮次间确定性：同一 mode 各轮的重建次数应相同")
for mode in ("ONLs", "ONLp"):
    rbs = []
    for R in (1, 2, 3):
        rows = CPP.get((mode, R))
        if rows: rbs.append(sum(1 for r in rows if r["rb"] == 1))
    if rbs:
        ok = "相同 ✓" if len(set(rbs)) == 1 else "★不同 %s" % rbs
        print("     %-6s 各轮重建数 = %s  %s" % (mode, rbs, ok))

print("\n  2) 迭代数确定性（从日志）")
log = os.path.join(P2, "a2l15.log")
if os.path.exists(log):
    it = defaultdict(list); wall = defaultdict(list)
    for ln in open(log, errors="ignore"):
        if not ln.startswith("round="): continue
        kv = dict(x.split("=") for x in ln.split() if "=" in x)
        m = kv.get("mode");
        if m: it[m].append(int(kv["iters"])); wall[m].append(int(kv["wall_ms"]))
    for m in ("K1", "K3", "ONLs", "ONLp"):
        if it[m]:
            ok = "相同 ✓" if len(set(it[m])) == 1 else "★不同"
            print("     %-6s iters=%s %s   墙钟中位=%d ms"
                  % (m, it[m], ok, st.median(wall[m])))

print("\n  3) csvuniq == nsteps（步数一致）")
bad = 0
for ln in open(log, errors="ignore") if os.path.exists(log) else []:
    if "csvuniq" in ln and "fatal" in ln:
        print("     %s" % ln.strip())
        break
print("\n  4) est>avg 的重建占比（判据是否退化）")
for (mode, R), rows in sorted(CPP.items()):
    post = [r for r in rows if r["t"] > B0]
    if not post: continue
    rb = sum(1 for r in post if r["rb"] == 1)
    ratio = 100.0*rb/len(post)
    flag = "  ★疑似退化（≈50% 周期2）" if 45 <= ratio <= 55 else ""
    print("     %-24s 预热后重建 %d/%d = %.1f%%%s"
          % ("%s_r%d" % (mode, R), rb, len(post), ratio, flag))

# ---------- 5. 墙钟对照（同轮交错，取中位） ----------
print("\n【墙钟对照】（同轮内交错，取 3 轮中位）")
if os.path.exists(log):
    wall = defaultdict(list)
    for ln in open(log, errors="ignore"):
        if not ln.startswith("round="): continue
        kv = dict(x.split("=") for x in ln.split() if "=" in x)
        if kv.get("mode"): wall[kv["mode"]].append(int(kv["wall_ms"]))
    base = st.median(wall["K1"]) if wall.get("K1") else None
    print("  %-8s %12s %12s" % ("mode", "墙钟中位", "相对 K1"))
    for m in ("K1", "K3", "ONLs", "ONLp"):
        if not wall.get(m): continue
        md = st.median(wall[m])
        rel = ("%+.1f%%" % (100*(md/base-1))) if base else "—"
        print("  %-8s %10d ms %12s" % (m, md, rel))

# ---------- 6. 与 l20 并排 ----------
print("\n【与 l20 并排】（同网格、同判据，仅 levels 不同）")
print("  %-6s %8s %10s %10s %10s" % ("配置", "levels", "重建", "预热后", "间隔中位"))
for tag, r_ in (("l15", r_single), ("l20", 90.61)):
    rows_ref = None
    for cand in ("a2l15_onl_ONLs_r2.csv", "a2A_onl_ONLs_r1.csv"):
        pass
print("  %-6s %8d %10d %10d %10s" % ("l15", 15, len(rbs_m), len(post_m),
                                      ("%.0f" % st.median(gaps_m)) if gaps_m else "-"))
l20rows = read_online(os.path.join(P2, "a2A_onl_ONLs_r1.csv"))
if l20rows:
    rb20 = [r["t"] for r in l20rows if r["rb"] == 1]
    po20 = [t for t in rb20 if t > B0]
    g20 = [po20[i+1]-po20[i] for i in range(len(po20)-1)] if len(po20) > 1 else []
    print("  %-6s %8d %10d %10d %10s" % ("l20", 20, len(rb20), len(po20),
                                          ("%.0f" % st.median(g20)) if g20 else "-"))
print("=" * 126)
