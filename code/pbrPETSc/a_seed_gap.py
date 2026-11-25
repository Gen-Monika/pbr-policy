#!/usr/bin/env python3
"""
★★★ 决定性验证：分歧的种子在 t=100（预热边界）

═══ 推理 ═══
K 扫描的口径是 FREEZE_BASE=100，即 t<100 每步重建、t=100 起按 K 周期重建。
具体到 t=100：(t-B0) % K == 0 → 对所有 K 都成立 ⇒ 【t=100 恒为重建步】。
因此【没有任何一个 K 扫描文件测量过 (t=100, a>0)】。

又因为：
  · 在 t=100 处，held=99（t=99 刚重建），所以该步的 age = 1
  · 这是策略在预热后【第一次真正复用】，也是 dN 表的第一个样本来源
⇒ (100, 1) 这个格子【必然缺失】，而它正是整个预热后轨迹的种子。

模型只能靠形状迁移【编造】它；C++ 则在运行时【真实测量】它。
若两者的差足够大，判据 (lvl+delta > avg) 这个刀刃比较就会翻向不同侧，
之后两条轨迹的采样集不同 ⇒ 无法重新对齐。

═══ 本脚本验证 ═══
1. 确认 (100, 1) 在实测表里确实缺失
2. 取 C++ 实测的 N(100,1)，与模型的形状迁移值比较
3. 用"真实值"替换该格子后，模型的重建次数是否向 C++ 靠拢
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0

SPEC_L20 = [("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
            ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])]


def load_l20():
    cells = defaultdict(list); rv = []; fac = []; ns = 0
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
                if len(steps) < 344: continue
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
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv), fac=st.median(fac), nsteps=ns)


def read_online(path):
    rows = []
    with open(path, errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                rows.append(dict(t=int(float(q[idx["timeIndex"]])),
                                 rb=int(float(q[idx["rebuild"]])),
                                 age=int(float(q[idx["runAge"]])),
                                 est=float(q[idx["est"]]),
                                 avg=float(q[idx["avg"]]),
                                 rMed=float(q[idx["rMed"]]),
                                 pN=float(q[idx["prevN"]])))
            except (ValueError, KeyError): pass
    return rows


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
            levels.append(N); a = 1; held = t; rbs.append(t); act = "R"
        else:
            N = env(t, a); tot += N; acc += N; accn += 1
            if levels:
                bm = st.median(levels)
                if bm > 1e-9: know[a].append(N - bm)
            a += 1; act = "u"
        trace.append(dict(t=t, act=act, age=age, N=N, lvl=lvl, delta=delta, avg=avg))
    return tot, rbs, trace, know, levels


cfg = load_l20()
T = cfg["nsteps"]; r_single = cfg["r1"]; r_eff = cfg["r1"]*cfg["fac"]
envS = P.Env(cfg["tab"], mode="real", interp="shape")

# C++ 实测的 N(100,1)
rows = read_online(os.path.join(P2, "a2smoke3_onl_ONLs_r1.csv"))
Ncpp = {}
for i, r in enumerate(rows):
    if i > 0 and r["pN"] > 0:
        Ncpp[rows[i-1]["t"]] = r["pN"]

print("=" * 122)
print("★★★ 1. (t=100, a>0) 是否在实测表里缺失？")
print("=" * 122)
for t in (98, 99, 100, 101, 102):
    ages = sorted(envS.byt.get(t, {}))
    print("  t=%-4d 实测可用年龄=%s" % (t, ages))
print()
print("  ⇒ t=100 的实测年龄只有 [0]（因为 t=100 对所有 K 都是重建步）")
print("     所以 (100, a=1) 必须由填充给出")

print()
print("=" * 122)
print("★★★ 2. 模型填充值 vs C++ 实测值")
print("=" * 122)
for t in (100, 101, 102, 103):
    mv = envS(t, 1)
    cv = Ncpp.get(t)
    print("  N(%-4d, 1): 模型形状迁移=%8.1f   C++ 实测=%s"
          % (t, mv, ("%.1f" % cv) if cv is not None else "—"))

print()
print("=" * 122)
print("★★★ 3. 把 C++ 实测的 (100,1) 注入模型，看重建次数是否靠拢")
print("=" * 122)


def stats_of(rbs):
    post = [t for t in rbs if t > B0]
    gaps = [post[i+1]-post[i] for i in range(len(post)-1)]
    return len(rbs), len(post), (st.median(gaps) if gaps else None)


print("  %-40s %8s %8s %8s" % ("口径", "重建", "预热后", "间隔中位"))
base = cfg["tab"]
tot0, rbs0, tr0, k0, l0 = sim_instr(envS, r_single, T)
s0 = stats_of(rbs0)
print("  %-40s %8d %8d %8s" % ("模型(纯形状迁移, r0=1×r)", s0[0], s0[1],
                               ("%.0f" % s0[2]) if s0[2] else "-"))

# 注入：把 C++ 实测的小年龄值加进表
for ncm in (1, 3, 5, 10):
    tab2 = dict(base)
    for t in range(B0, B0 + ncm):
        for aa in (1, 2, 3):
            if t in Ncpp and aa == 1 and Ncpp[t] > 0:
                tab2[(t, aa)] = Ncpp[t]
    # 用 C++ 的年龄序列也权当参考
    env2 = P.Env(tab2, mode="real", interp="shape")
    tot, rbs, tr, kk, ll = sim_instr(env2, r_single, T)
    s = stats_of(rbs)
    print("  %-40s %8d %8d %8s" % ("注入 C++ 实测的 (t<100+%d, 1)" % ncm,
                                   s[0], s[1], ("%.0f" % s[2]) if s[2] else "-"))

# C++ 参考
R = read_online(os.path.join(P2, "a2smoke3_onl_ONLs_r1.csv"))
rb = [r["t"] for r in R if r["rb"] == 1]
s = stats_of(rb)
print("  %-40s %8d %8d %8s" % ("★ C++ 实测（a2smoke3 ONLs）", s[0], s[1],
                               ("%.0f" % s[2]) if s[2] else "-"))

print()
print("=" * 122)
print("★★★ 4. 逐步决策一致性（模型 vs C++）")
print("=" * 122)
byt = {x["t"]: x for x in tr0}
agree = dis = 0
first_dis = None
for r in R:
    t = r["t"]
    if t <= B0 or t not in byt: continue
    m = "R" if byt[t]["act"] == "R" else "u"
    c = "R" if r["rb"] == 1 else "u"
    if m == c: agree += 1
    else:
        dis += 1
        if first_dis is None: first_dis = (t, c, m)
print("  预热后逐步决策：一致=%d  不一致=%d  (一致率 %.1f%%)"
      % (agree, dis, 100.0*agree/max(1, agree+dis)))
if first_dis:
    print("  首次分歧在 t=%d：C++ 选择 %s，模型选择 %s"
          % (first_dis[0], "重建" if first_dis[1] == "R" else "复用",
             "重建" if first_dis[2] == "R" else "复用"))
print("=" * 122)
