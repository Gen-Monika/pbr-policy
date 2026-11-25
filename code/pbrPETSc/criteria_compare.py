#!/usr/bin/env python3
"""
★★★ 判据的规范化检验：ΔN_step(K) 与 r/s 的交叉点

★ 关键：把"决策量"统一为【每步平均迭代增量】与【阈值 r/s】，两者都抗波动。
  判据：ΔN_step(K) < r/s  ⇒ 复用胜出
"""
import os, re, statistics as st
from collections import defaultdict

WL_B = re.compile(r"round=(\d+)\s+K=(\d+)\s+wall_ms=(\d+)\s+execTime=([0-9.]+)")
SOLVE_RE = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
TIME_RE  = re.compile(r"^Time = ([0-9.eE+-]+)\s*$")

def per_step_N(path):
    out, cur = [], []
    for ln in open(path, errors="ignore"):
        if TIME_RE.match(ln):
            if cur: out.append(sum(cur))
            cur = []
            continue
        m = SOLVE_RE.search(ln)
        if m: cur.append(int(m.group(1)))
    if cur: out.append(sum(cur))
    return out

def case(name, outfile, logdir, logpat, rval, s=3):
    W = defaultdict(dict)
    for ln in open(outfile):
        m = WL_B.search(ln)
        if m: W[int(m.group(1))][int(m.group(2))] = float(m.group(4))
    ks = sorted({k for r in W.values() for k in r})
    # 迭代数
    N = {}
    for K in ks:
        ns = []
        for r in sorted(W):
            p = os.path.join(logdir, logpat % (r, K))
            if os.path.exists(p):
                v = per_step_N(p)
                if v: ns.append(sum(v))
        if ns: N[K] = st.median(ns)
    print("=" * 104)
    print("  %s   r=%.2f   阈值 r/s=%.2f   (s=%d)" % (name, rval, rval/s, s))
    print("=" * 104)
    print("  %4s %10s %10s %14s %16s %10s %10s" %
          ("K","步数","Σ迭代数","相对K=1","ΔN_step(相对)","判定","墙钟/s"))
    b = N.get(1)
    nstp = None
    for K in ks:
        if K not in N: continue
        # 步数从日志行数取
        p = os.path.join(logdir, logpat % (sorted(W)[0], K))
        nstp = len(per_step_N(p)) if os.path.exists(p) else 0
        dn = (N[K]-b)/max(nstp,1)
        ok = dn < rval/s
        wt = st.median([W[r][K] for r in W if K in W[r]])
        print("  %4d %10d %10d %13.2f%% %16.1f %10s %10.2f"
              % (K, nstp, N[K], (N[K]/b-1)*100 if b else 0, dn,
                 "复用 ✓" if ok else "重建 ✗", wt))
    # 交叉点
    cross = [K for K in ks if K in N and (N[K]-b)/max(nstp,1) >= rval/s]
    if cross:
        print("\n  ⇒ 判据：首次失效于 K=%d ⇒ 预测可复用到 K=%d" % (cross[0], cross[0]-1))
    else:
        print("\n  ⇒ 判据：在扫描范围内未失效")
    print("  ⇒ 实测最优 K = %d" % min(ks, key=lambda K: st.median([W[r][K] for r in W if K in W[r]])))
    print()

case("base 网格 L20 (2268 单元)", "l20.out", "/root/autodl-tmp/PBR/l20",
     "log.r%dk%d", 90.79)
case("fine 网格 L20 (9072 单元)", "fine_scan.out", "/root/autodl-tmp/PBR/finerun",
     "log.r%dk%d", 114.83)

print("""
  ★★ 判据的规范化结论：
    阈值 r/s 随 r 上升（这是"r 越大决策空间越宽"的来源）；
    但 ΔN_step(K) 的【陡度】也随算例变化。
    两者共同决定最优 K ⇒ 最优 K 不是 r 的单调函数。

  ★★★ 最抗波动的报告方式：
    给出 (r, s, ΔN_step(K) 曲线) 这三样，而不是只给"最优 K=某值"。
    因为前两者分别是比值与离散量，都不受机器效率波动影响。
""")
