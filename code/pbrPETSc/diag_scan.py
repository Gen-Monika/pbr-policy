#!/usr/bin/env python3
"""诊断：为什么同一 K 的三次重复，ΣN·tIter 相差 29%（而 N 序列相同）。"""
import os
import re
import statistics as st

HDR20 = ("timeIndex,field,kind,levels,nCells,nFaces,reps,freezeAt,reused,period,"
         "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,ma,mp,tIter,r,rTotal").split(",")


def load_csv(path):
    rows = []
    for ln in open(path):
        p = ln.rstrip("\n").split(",")
        cols = HDR20 if len(p) == 20 else None
        if cols is None:
            continue
        d = {}
        try:
            for k, v in zip(cols, p):
                d[k] = v if k in ("field", "kind") else float(v)
        except ValueError:
            continue
        rows.append(d)
    return rows


def load_N(logpath):
    pat = re.compile(r"Solving for p_rgh.*?No Iterations\s+(\d+)")
    N = []
    for ln in open(logpath, errors="ignore"):
        if "p_rgh" not in ln:
            continue
        m = pat.search(ln)
        if m:
            N.append(int(m.group(1)))
    return N


print("=" * 92)
print("诊断：同一 K 的重复之间，tIter 与 N 的一致性")
print("=" * 92)
print(f"{'K':>2} {'rep':>3} {'csv行':>6} {'log N数':>7} {'ΣN':>7} {'中位tIter/µs':>13} "
      f"{'ΣN·tIter/ms':>12} {'中位ma/µs':>11} {'中位mp/µs':>11} {'重建tSetup/µs':>13}")

for K in (1, 2, 3, 4, 5, 6, 8):
    for rep in (1, 2, 3):
        csvp = f"s_k{K}_r{rep}.csv"
        logp = f"s{K}/log.s{rep}"
        if not (os.path.exists(csvp) and os.path.exists(logp)):
            continue
        rows = load_csv(csvp)
        N = load_N(logp)
        n = min(len(rows), len(N))
        sN = sum(N[:n])
        sNt = sum(Ni * d["tIter"] for Ni, d in zip(N[:n], rows[:n]))
        ti = st.median([d["tIter"] for d in rows])
        ma = st.median([d["ma"] for d in rows])
        mp = st.median([d["mp"] for d in rows])
        reb = [d["tPCSetup"] for d in rows if d["reused"] == 0]
        print(f"{K:>2} {rep:>3} {len(rows):>6} {len(N):>7} {sN:>7} "
              f"{ti*1e6:>13.2f} {sNt*1e3:>12.2f} {ma*1e6:>11.2f} {mp*1e6:>11.2f} "
              f"{st.median(reb)*1e6:>13.1f}")

print()
print("=" * 92)
print("关键：N 序列本身在各重复间是否相同？")
print("=" * 92)
for K in (2, 3, 4, 5, 6, 8):
    seqs = []
    for rep in (1, 2, 3):
        logp = f"s{K}/log.s{rep}"
        if os.path.exists(logp):
            seqs.append(load_N(logp))
    if len(seqs) < 2:
        continue
    same = all(s == seqs[0] for s in seqs)
    diffs = sum(1 for a, b in zip(seqs[0], seqs[1]) if a != b) if len(seqs) > 1 else 0
    print(f"  K={K}: 长度 {[len(s) for s in seqs]}  "
          f"{'完全相同 ✓' if same else f'不同 ✗（rep1 vs rep2 有 {diffs} 处不同）'}")

print()
print("=" * 92)
print("参照：K=1 与各 K 的 N 序列在第 100 步附近（冻结刚生效）")
print("=" * 92)
for K in (1, 2, 3, 5, 8):
    logp = f"s{K}/log.s1"
    if not os.path.exists(logp):
        continue
    N = load_N(logp)
    print(f"  K={K}: N[98:112] = {N[98:112]}")
