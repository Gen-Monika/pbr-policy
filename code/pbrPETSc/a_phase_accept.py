#!/usr/bin/env python3
"""
★★★ 相位扫描数据的验收测试（跑全量之前必须通过）

═══ 验收标准 ═══
用相位扫描数据建 N(t,a) 表，然后：
  测试1  (100,1) 必须是【实测值】，不再是填充
  测试2  用它跑模型在线策略，重建次数应接近 C++ 实测的 221/122
  测试3  逐步决策一致率应显著高于此前的 51.2%
  测试4  与 K 扫描数据的一致性：两者都在同一 t 上测过某些 (t,a)，
         这些重叠格子的值应当接近

测试2/3 是决定性的：若模型现在能复现 C++，说明"分歧源于数据空洞"
这个诊断成立，且相位扫描修好了它。
"""
import sys, os, statistics as st
from collections import defaultdict
sys.path.insert(0, "/root/autodl-tmp/PBR")
import pbrlib as P

P2 = "/root/autodl-tmp/PBR"
B0 = P.B0
T = 344


def load_phase(tag="phsmoke", pfx="l20", A=3):
    """读相位扫描的 CSV+log，返回 (tab, rv, fac, files)"""
    K = A + 1
    cells = defaultdict(list); rv = []; fac = []; files = []
    for B in range(B0 - A, B0 + 1):
        c = os.path.join(P2, "%s_%s_B%d_K%d_r1.csv" % (tag, pfx, B, K))
        l = os.path.join(P2, "%s_l20", tag,
                         "log.B%dK%d_r1" % (B, K))
        if not (os.path.exists(c) and os.path.exists(l)):
            # 日志在 workdir 下
            l2 = os.path.join(P2, "%s_l20" % tag, "log.B%dK%d_r1" % (B, K))
            if not (os.path.exists(c) and os.path.exists(l2)):
                continue
            l = l2
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
        files.append((B, len(steps)))
    return dict(tab={k: st.median(v) for k, v in cells.items()},
                r1=st.median(rv) if rv else float("nan"),
                fac=st.median(fac) if fac else 1.0, files=files)


def load_kscan():
    """K 扫描（已有数据），用于重叠一致性检查"""
    cells = defaultdict(list)
    for pfx, logdir, Ks, rounds in (("l20", "l20", [1,2,3,5,8], [1,2,3,4,5]),
                                    ("covscan_l20", "covscan_l20", [13,20,30], [1,2,3])):
        for K in Ks:
            for R in rounds:
                c = os.path.join(P2, "%s_pc_k%d_r%d.csv" % (pfx, K, R))
                l = os.path.join(P2, logdir, "log.r%dk%d" % (R, K))
                if not (os.path.exists(c) and os.path.exists(l)): continue
                rr = P.rows(c); seen = {}
                for x in rr:
                    if int(x["rep"]) >= 0 and int(x["timeIndex"]) not in seen:
                        seen[int(x["timeIndex"])] = x
                steps = [seen[t] for t in sorted(seen)]
                if len(steps) < T: continue
                Ns = P.per_step_N(l); n = min(len(steps), len(Ns))
                for i in range(n):
                    x = steps[i]; rf = int(x["reusedFrom"])
                    cells[(i+1, 0 if rf < 0 else i+1-rf)].append(Ns[i])
    return {k: st.median(v) for k, v in cells.items()}


# C++ 实测参考
def cpp_ref():
    rows = []
    with open(os.path.join(P2, "a2smoke3_onl_ONLs_r1.csv"), errors="ignore") as f:
        hdr = f.readline().rstrip("\n").split(",")
        idx = {k: i for i, k in enumerate(hdr)}
        for ln in f:
            q = ln.rstrip("\n").split(",")
            if len(q) != len(hdr): continue
            try:
                rows.append(dict(t=int(float(q[idx["timeIndex"]])),
                                 rb=int(float(q[idx["rebuild"]])),
                                 pN=float(q[idx["prevN"]])))
            except (ValueError, KeyError): pass
    N = {}
    for i, r in enumerate(rows):
        if i > 0 and r["pN"] > 0: N[rows[i-1]["t"]] = r["pN"]
    rb = [r["t"] for r in rows if r["rb"] == 1]
    return N, rb, rows


def sim_instr(env, r0, Tn):
    know = defaultdict(list); levels = []
    tot = 0.0; a = 0; acc = 0.0; accn = 0; held = -1
    rbs = []; trace = []
    for t in range(1, Tn+1):
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


print("=" * 122)
print("★★★ 相位扫描数据验收（phsmoke, l20, A=3, K=4）")
print("=" * 122)
ph = load_phase()
ks = load_kscan()
Ncpp, rbcpp, rowscpp = cpp_ref()
print("  相位扫描文件: %s" % ph["files"])
print("  相位扫描格子数=%d   K扫描格子数=%d" % (len(ph["tab"]), len(ks)))
print("  r（单次分解）=%.2f   s=%.2f   r_eff=%.1f" % (ph["r1"], ph["fac"], ph["r1"]*ph["fac"]))

print()
print("─" * 122)
print("测试1：(t=100, a=1) 是否实测到？")
print("─" * 122)
v = ph["tab"].get((100, 1))
print("  相位扫描 N(100,1) = %s" % (("%.1f" % v) if v is not None else "★缺失（仍是填充）"))
print("  C++ 实测  N(100,1) = %.1f" % Ncpp.get(100, float("nan")))
if v is not None:
    print("  ⇒ 实测到了，误差 %+.1f%%" % (100*(v/Ncpp[100]-1)))
    print("  （此前模型靠形状迁移填的是 33.2，与实测 41.0 差 -19%%）")
    print("     而 K 扫描里该格子存在吗？ %s"
          % ("在" if (100,1) in ks else "★不在（正是空洞所在）"))

print()
print("─" * 122)
print("测试2/3：用相位扫描数据跑模型在线，与 C++ 实测对照")
print("─" * 122)
r_single = ph["r1"]
for nm, srcd, r0v, ip in (("相位扫描", ph["tab"], r_single, "shape"),
                          ("相位扫描", ph["tab"], r_single*ph["fac"], "shape"),
                          ("K扫描(旧)", ks, r_single, "shape"),
                          ("K扫描(旧)", ks, r_single*3, "shape")):
    env = P.Env(srcd, mode="real", interp=ip)
    tot, rbs, tr, know, levels = sim_instr(env, r0v, T)
    post = [t for t in rbs if t > B0]
    gaps = [post[i+1]-post[i] for i in range(len(post)-1)] if len(post) > 1 else []
    # 逐步一致率
    byt = {x["t"]: x for x in tr}
    agree = dis = 0
    for r in rowscpp:
        t = r["t"]
        if t <= B0 or t not in byt: continue
        if (byt[t]["act"] == "R") == (r["rb"] == 1): agree += 1
        else: dis += 1
    print("  %-12s r0=%-7.1f 重建=%-4d 预热后=%-4d 间隔中位=%-4s 一致率=%.1f%%"
          % (nm, r0v, len(rbs), len(post),
             ("%.0f" % st.median(gaps)) if gaps else "-",
             100.0*agree/max(1, agree+dis)))
print("  %-12s         重建=%-4d 预热后=%-4d 间隔中位=%-4s"
      % ("★ C++ 实测", len(rbcpp), len([t for t in rbcpp if t > B0]), "2"))

print()
print("─" * 122)
print("测试4：相位扫描 与 K 扫描 在重叠格子上的值是否一致")
print("─" * 122)
overlap = set(ph["tab"]) & set(ks)
if overlap:
    rats = [ph["tab"][k]/ks[k] for k in overlap if ks[k] > 1e-9]
    print("  重叠格子=%d  比值(相位/K): 中位=%.3f  均值=%.3f  范围=[%.3f, %.3f]"
          % (len(overlap), st.median(rats), sum(rats)/len(rats), min(rats), max(rats)))
    print("  ⇒ 中位接近 1.0 说明两批数据互相印证（同一算例、同口径）")
    # 只看小年龄（决定决策的那些）
    small = [k for k in overlap if k[1] <= 3]
    if small:
        rs = [ph["tab"][k]/ks[k] for k in small if ks[k] > 1e-9]
        print("  其中 age≤3 的格子=%d  比值中位=%.3f"
              % (len(small), st.median(rs)))
else:
    print("  ★ 无重叠格子")
print("=" * 122)
