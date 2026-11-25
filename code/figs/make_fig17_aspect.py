#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Figure 17: external validation on ASPECT / Blankenbach case 2a.
Data source: aspect_its.json (exported on the server by /root/figdat.py from cmp_l5_t0.1/r1_*/run.log;
iteration counts are deterministic and identical across 3 rounds, so round 1 is used).
(a) Average Stokes iterations per 100 steps for each policy; (b) rebuild instants of the online policy (after warm-up).
"""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.sans-serif": ["Noto Sans CJK JP", "Noto Sans CJK SC",
                        "Droid Sans Fallback", "DejaVu Sans"],
    "font.family": "sans-serif", "axes.unicode_minus": False,
    "font.size": 11, "axes.labelsize": 11.5, "xtick.labelsize": 10,
    "ytick.labelsize": 10, "legend.fontsize": 9.5,
    "figure.dpi": 160, "savefig.dpi": 160, "savefig.bbox": "tight",
    "axes.grid": True, "grid.alpha": 0.28, "grid.linestyle": "--",
    "axes.axisbelow": True,
})
C_MAIN, C_SAFE, C_BEST, C_DANGER, C_WARN = "#1f4e79", "#7f7f7f", "#2e8b57", "#c0392b", "#e08214"

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "aspect_its.json"), encoding="utf-8"))
OUT = os.environ.get("FIGOUT", os.path.abspath(os.path.join(HERE, "..", "..", "paper", "figs")))

B = 100
def binned(v):
    v = np.asarray(v, float)
    n = len(v) // B
    return np.arange(n) * B + B / 2, v[: n * B].reshape(n, B).mean(1)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True,
                               gridspec_kw={"height_ratios": [2.2, 1]})
style = {
    "K1":     ("Official default $K=1$ (rebuild every step)", C_SAFE, "-", 2.0),
    "K25":    ("Fixed period $K=25$ (near the best in hindsight)", C_BEST, "--", 1.8),
    "NEVER":  ("Never rebuild", C_DANGER, ":", 2.2),
    "ONLINE": ("Online policy (this paper, zero tuning)", C_MAIN, "-", 2.4),
}
for k, (lab, c, ls, lw) in style.items():
    x, y = binned(D[k])
    ax1.plot(x, y, ls, color=c, lw=lw, label=lab, marker="o", ms=3.5)
ax1.set_ylabel("Average GMRES iterations\nper Stokes solve")
ax1.set_title("(a) Average iterations per 100 steps: the online policy sits slightly above $K=1$/$K=25$ during the long reuse stretch\nand rejoins them once rapid ageing begins; never-rebuild stays high throughout", fontsize=11.5)
ax1.legend(loc="upper right")

rb = [s for s in D["online_rebuild_steps"] if s >= 100]
ax2.axvspan(0, 100, color=C_WARN, alpha=0.15, lw=0)
ax2.text(50, 0.5, "warm-up\n(rebuild every step)", ha="center", va="center", fontsize=9.5, color=C_WARN)
ax2.vlines(rb, 0, 1, color=C_MAIN, lw=1.8)
for a, b in zip(rb, rb[1:]):
    ax2.annotate("", (b, 0.82), (a, 0.82),
                 arrowprops=dict(arrowstyle="<->", color="#555", lw=0.8))
    w = b - a
    rot = 90 if w < 0.04 * len(D["K1"]) else 0
    ax2.text((a + b) / 2, 0.88, str(w), ha="center", va="bottom", fontsize=8.5,
             color="#333", rotation=rot)
ax2.set_ylim(0, 1.32); ax2.set_yticks([])
ax2.set_xlabel("Time step")
ax2.set_title("(b) Rebuild instants and intervals of the online policy after warm-up\n(round 1; the three rounds differ by at most one step before step 1119, then diverge with the online-measured $\\rho$)", fontsize=11.5)
ax2.set_xlim(0, len(D["K1"]))
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig17_aspect_blankenbach.png"))
print("saved", os.path.join(OUT, "fig17_aspect_blankenbach.png"))
