#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两项测量：
A. 短跨度配置的净漂移是否可信（fx/l15/l20 只有 248 帧）
B. 决策相关变差 eta 与形状变差 V_shape 的相对大小

A 的问题
--------
`a_vt_net.py` 的 net 是「首末窗口两个均值之差」，只有一对样本。fx/l15/l20 的
T=344、有效帧 248，去程/回程任一端异常就会造出假的「单向漂移」。相位表不超过 T，
无法拉长跨度，所以在现有跨度内改用**分块配对**：

  把帧序列切成若干互不重叠的长度 L 块，对每一对相邻块算 max_a|m_{i+1}(a)-m_i(a)|，
  再看这批差值的分布。真漂移：全部同号且量级接近；端点偶然：正负混杂、方差大。

同时给 rolling 估计：对每个起点 t0 取 (t0, t0+L) 的净位移，报其符号一致率。

B 的定义
--------
  c_t(K) = mean_{a<K} N(t,a) + rho/K         （rho 取该配置实测 r1）
  eta_t  = max_{K in 1..Kmax} |c_t(K) - c_{t-1}(K)|
  Eta_sum = sum_t eta_t
与同口径的 V_shape 求和对比，得到「商空间比总变差小多少」。
"""
import json
import os
import statistics as st
import sys

P2 = os.environ.get("P2", "/root/autodl-tmp/PBR")
sys.path.insert(0, os.environ.get("PBR_CODE", "."))
from pbrcost import ORDER, load_phase  # noqa: E402

OUT = os.environ.get("OUT", "/root/autodl-tmp/PBR_vt_20261031/vt_eta.json")
LONGS = (25, 50, 100)      # 分块长度
KMAX = 20


def frames_of(tab):
    ts = sorted({t for (t, _a) in tab})
    as_ = sorted({a for (_t, a) in tab})
    fr = {}
    for t in ts:
        p = {a: tab[(t, a)] for a in as_ if (t, a) in tab}
        if 0 in p and len(p) >= 4:
            fr[t] = p
    return fr


def gvec(p):
    return {a: p[a] - p[0] for a in p if a > 0}


def block_pairs(fr, L):
    """互不重叠的相邻块间形状差；返回 [(diff, sign)]。"""
    ts = sorted(fr)
    means = []
    for i in range(0, len(ts), L):
        chunk = ts[i:i + L]
        if len(chunk) < max(5, L // 3):
            continue
        gs = [gvec(fr[t]) for t in chunk]
        common = set(gs[0])
        for g in gs[1:]:
            common &= set(g)
        common = sorted(common)
        if not common:
            continue
        means.append({a: st.mean(g[a] for g in gs) for a in common})
    out = []
    for m0, m1 in zip(means, means[1:]):
        common = sorted(set(m0) & set(m1))
        if not common:
            continue
        signed = [m1[a] - m0[a] for a in common]
        # 幅度取 max，符号取「绝对值最大那个 age 的符号」
        am = max(range(len(signed)), key=lambda i: abs(signed[i]))
        out.append((abs(signed[am]), signed[am]))
    return out


def rolling_pairs(fr, L):
    """每个起点 t0 的 (t0, t0+L) 净位移与符号。"""
    ts = sorted(fr)
    gm = {}
    for t in ts:
        g = gvec(fr[t])
        if g:
            gm[t] = g
    out = []
    for i, t0 in enumerate(ts):
        t1 = t0 + L
        if t1 not in gm or t0 not in gm:
            continue
        g0, g1 = gm[t0], gm[t1]
        common = sorted(set(g0) & set(g1))
        if not common:
            continue
        signed = [g1[a] - g0[a] for a in common]
        am = max(range(len(signed)), key=lambda i: abs(signed[i]))
        out.append((abs(signed[am]), signed[am]))
    return out


def eta_series(fr, rho):
    """决策相关变差：c_t(K) 的逐 t 变化。"""
    ts = sorted(fr)
    cs = {}
    for t in ts:
        p = fr[t]
        v = {}
        for K in range(1, KMAX + 1):
            ages = [a for a in range(K) if a in p]
            if len(ages) < K:
                break
            v[K] = st.mean(p[a] for a in ages) + rho / K
        if len(v) >= 2:
            cs[t] = v
    eta, vshape = [], []
    ts2 = [t for t in ts if t in cs]
    for t0, t1 in zip(ts2, ts2[1:]):
        v0, v1 = cs[t0], cs[t1]
        common = sorted(set(v0) & set(v1))
        if not common:
            continue
        eta.append(max(abs(v1[K] - v0[K]) for K in common))
        g0, g1 = gvec(fr[t0]), gvec(fr[t1])
        cc = sorted(set(g0) & set(g1))
        if cc:
            vshape.append(max(abs(g1[a] - g0[a]) for a in cc))
    return eta, vshape, len(ts2)


def main():
    out = {"kind": "VT_eta_and_blockpairs", "P2": P2, "cases": {}}
    for tag in ORDER:
        try:
            ph = load_phase(tag, verbose=False)
        except Exception as exc:                      # noqa: BLE001
            out["cases"][tag] = {"error": repr(exc)}
            continue
        if not ph:
            out["cases"][tag] = {"error": "None"}
            continue
        fr = frames_of(ph["tab"])
        rho = ph.get("r1") or 10.0
        eta, vsh, nfr = eta_series(fr, rho)
        e = {"n_frames": len(fr), "rho": rho, "T": ph.get("T"),
             "eta_sum": round(sum(eta), 2),
             "vshape_sum": round(sum(vsh), 2),
             "eta_per_step": round(st.mean(eta), 4) if eta else None,
             "vshape_per_step": round(st.mean(vsh), 4) if vsh else None,
             "ratio_eta_over_vshape": (round(st.mean(eta) / st.mean(vsh), 4)
                                       if eta and vsh and st.mean(vsh) else None),
             "blocks": {}, "rolling": {}}
        for L in LONGS:
            bp = block_pairs(fr, L)
            if bp:
                mags = [m for m, _s in bp]
                pos = sum(1 for _m, s in bp if s > 0)
                e["blocks"][str(L)] = {
                    "n": len(bp), "mean": round(st.mean(mags), 2),
                    "median": round(st.median(mags), 2),
                    "stdev": round(st.pstdev(mags), 2) if len(mags) > 1 else 0.0,
                    "frac_positive": round(pos / len(bp), 2),
                    "mags": [round(m, 1) for m in mags]}
            rp = rolling_pairs(fr, L)
            if rp:
                mags = [m for m, _s in rp]
                pos = sum(1 for _m, s in rp if s > 0) / len(rp)
                e["rolling"][str(L)] = {
                    "n": len(rp), "median": round(st.median(mags), 2),
                    "mean": round(st.mean(mags), 2),
                    # 符号一致率：0.5 = 无方向；接近 0 或 1 = 单向
                    "frac_positive": round(pos, 3),
                    "sign_agreement": round(abs(pos - 0.5) * 2, 3)}
        out["cases"][tag] = e
        print("%-5s frames=%-5d eta/step=%-7s vshape/step=%-7s ratio=%-7s | "
              "rolling: %s" % (
                  tag, e["n_frames"], e["eta_per_step"], e["vshape_per_step"],
                  e["ratio_eta_over_vshape"],
                  " ".join("L%s med=%.1f agr=%.2f" % (
                      L, e["rolling"][str(L)]["median"], e["rolling"][str(L)]["sign_agreement"])
                      for L in LONGS if str(L) in e["rolling"])))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nwrote %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
