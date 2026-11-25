#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Figure-generation script for the 16 figures of the main text (English build).

Data source: figdata.json in this directory (versioned with the repository).
  Every number in the figures comes from that file; do not hard-code paper numbers in the plotting code.
Font: the default sans-serif is used; no CJK font is required for the English build.
Figure numbers come from the LaTeX \caption, so no "Figure N" title is embedded in the images.
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
if os.environ.get("FIGFONT"):
    font_manager.fontManager.addfont(os.environ["FIGFONT"])
from matplotlib.patches import Rectangle

plt.rcParams.update({
    "font.sans-serif": ["Noto Sans CJK JP", "Noto Sans CJK SC",
                        "Droid Sans Fallback", "DejaVu Sans"],
    "font.family": "sans-serif",
    "axes.unicode_minus": False,
    "font.size": 11, "axes.titlesize": 12.5, "axes.labelsize": 11.5,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
    "figure.dpi": 160, "savefig.dpi": 160, "savefig.bbox": "tight",
    "axes.grid": True, "grid.alpha": 0.28, "grid.linestyle": "--",
    "axes.axisbelow": True,
})

C_MAIN   = "#1f4e79"
C_SAFE   = "#7f7f7f"
C_BEST   = "#2e8b57"
C_DANGER = "#c0392b"
C_WARN   = "#e08214"
C_NEUT   = "#5b9bd5"
C_LIGHT  = "#a6a6a6"

_HERE = os.path.dirname(os.path.abspath(__file__))
FIGDATA = os.environ.get("FIGDATA", os.path.join(_HERE, "figdata.json"))
OUT = os.environ.get("FIGOUT",
      os.path.abspath(os.path.join(_HERE, "..", "..", "paper", "figs")))
os.makedirs(OUT, exist_ok=True)
D = json.load(open(FIGDATA, encoding="utf-8"))
print("Data source:", FIGDATA)
print("Output to:", OUT)

def save(fig, name):
    fig.savefig(os.path.join(OUT, name)); plt.close(fig); print("  saved", name)

def ann(ax, x, y, s, color="black", **kw):
    ax.annotate(s, (x, y), fontsize=9.5, color=color,
                ha=kw.pop("ha", "center"), va=kw.pop("va", "bottom"),
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color,
                          lw=0.8, alpha=0.9), **kw)

MAIN = ["fx", "l15", "l20", "fl30"]
SIDE = ["x3", "fine"]
BOUND = ["sth"]
ALL7 = MAIN + SIDE + BOUND


def fig1():
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    n = 14
    for t in range(n):
        d = t / (n - 1)
        col = (1 - 0.55 * d, 0.75 - 0.35 * d, 0.85 - 0.1 * d)
        ax.add_patch(Rectangle((t, 0), 0.82, 1.0, fc=col, ec="#404040", lw=0.9))
        ax.text(t + 0.41, 0.5, "$A_{%d}$" % (t + 1), ha="center", va="center", fontsize=10.5)
    ax.annotate("", xy=(n - 0.05, -0.62), xytext=(0, -0.62),
                arrowprops=dict(arrowstyle="->", lw=1.6, color="#404040"))
    ax.text(n / 2, -1.00, "Physical time advance: the operator $A_t$ drifts gradually (darker with time)", ha="center", fontsize=11)
    for xpos, tx in [(3.41, 1.9), (10.41, 11.9)]:
        ax.plot([xpos, xpos], [1.05, 1.55], color=C_BEST, lw=2)
        ax.annotate("Rebuild (pay $\\rho$)", xy=(xpos, 1.5), xytext=(tx, 1.95),
                    fontsize=10, color=C_BEST, ha="center",
                    arrowprops=dict(arrowstyle="->", color=C_BEST, lw=1.1))
    ax.add_patch(Rectangle((3.82, -0.16), 6.18, 0.14, fc=C_MAIN, ec="none", alpha=0.75))
    ax.text(6.9, -0.34, "Reuse (pay $N(t,a)$, no rebuild cost)", ha="center", fontsize=10.5, color=C_MAIN)
    for x0, a in [(4.2, 1), (5.2, 2), (6.2, 3)]:
        ax.text(x0, 1.06, "age $a=%d$" % a, ha="center", va="bottom",
                rotation=90, fontsize=8.5, color="#555")
    ax.set_xlim(-0.4, n + 0.3); ax.set_ylim(-1.30, 2.45); ax.axis("off")
    save(fig, "fig01_problem_setup.png")


def fig2():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.3))
    a = D["aging"]["col"]["a"]; N = D["aging"]["col"]["N"]
    ax1.plot(a[:6], N[:6], "o-", color=C_NEUT, lw=2, ms=7, label="Linear growth, $a\\in[0,7]$")
    ax1.plot(a[4:], N[4:], "o-", color=C_DANGER, lw=2.4, ms=7.5, label="After the transition ($a\\geq 8$)")
    k = (N[4] - N[0]) / (a[4] - a[0])
    ax1.plot(a[:5], [N[0] + k * (x - a[0]) for x in a[:5]], ":", color="#888",
             lw=1.6, label="Endpoint average increment for $a\\leq 7$ (%.2f per step)" % k)
    ax1.axvline(7.5, color=C_DANGER, ls="-.", lw=1.3, alpha=0.7)
    ann(ax1, 8.2, N[5] * 0.42, "3.7-fold jump\n382 → 1413", C_DANGER, ha="left")
    ax1.set_xlabel("Preconditioner age $a$ (steps)")
    ax1.set_ylabel("Iterations in that step, $N_{\\rm step}(a)$")
    ax1.set_title("(a) Phase-transition jump (measured, fx)", fontsize=11.5)
    ax1.set_yscale("log"); ax1.legend(loc="upper left", fontsize=9.5)
    d = D["aging"]["diag"]["N"]
    ax2.semilogy(range(len(d)), d, "s-", color=C_WARN, lw=2, ms=7)
    ax2.set_xlabel("Steps after the rebuild"); ax2.set_ylabel("Iteration count")
    ax2.set_title("(b) A diagonal preconditioner is more extreme (62 → 9575)", fontsize=11.5)
    ann(ax2, 3, d[3] * 0.25, "about 2.2 per step", C_WARN)
    save(fig, "fig02_aging_phase_transition.png")


def fig3():
    nr = D["never_rebuild"]
    x = np.arange(len(nr["cfg"]))
    fig, ax = plt.subplots(figsize=(9.4, 4.4))
    ax.bar(x - 0.19, nr["lower"], 0.36, color=C_MAIN,
           label="Age-effect frozen (physical-time drift retained)")
    ax.bar(x + 0.19, nr["upper"], 0.36, color=C_LIGHT, label="Archived linear-tail scenario")
    ax.set_yscale("log")
    ax.axhline(1.0, color=C_BEST, ls="--", lw=1.5, label="Best fixed period = 1×")
    for i, (lo, up) in enumerate(zip(nr["lower"], nr["upper"])):
        ax.text(i - 0.19, lo * 1.10, "%.1f×" % lo, ha="center", fontsize=9.5,
                color=C_MAIN, fontweight="bold")
        ax.text(i + 0.19, up * 1.12, "%.0f×" % up, ha="center", fontsize=9, color="#666")

    ax.set_xticks(x)
    ax.set_xticklabels(["%s\n(final age %d)" % (c, e) for c, e in zip(nr["cfg"], nr["extrap"])])
    ax.set_ylabel("Never-rebuild cost / best fixed period (log scale)")
    ax.set_ylim(0.45, 1500)
    ax.legend(loc="upper left", fontsize=9.5)
    save(fig, "fig03_never_rebuild_cost.png")


def fig4():
    cfgs = ["fx", "l15", "l20", "fl30", "x3", "fine"]
    fig, axes = plt.subplots(2, 3, figsize=(12.2, 6.4))
    for ax, t in zip(axes.ravel(), cfgs):
        cc = D["cost_curve"][t]
        ax.plot(cc["r1"]["K"], cc["r1"]["rel"], "o-", color=C_MAIN, lw=1.9,
                ms=5.5, label="$\\rho=r_1$")
        ax.plot(cc["sr1"]["K"], cc["sr1"]["rel"], "s--", color=C_WARN, lw=1.7,
                ms=5, label="$\\rho=s\\,r_1$")
        ax.axhline(0, color=C_BEST, ls="-.", lw=1.4)
        ax.scatter([1, 1], [cc["r1"]["rel"][0], cc["sr1"]["rel"][0]], marker="*",
                   s=130, color=C_SAFE, zorder=5, edgecolor="white", lw=0.6)
        ax.set_title(t, fontsize=11)
        ax.set_xlabel("Period $K$"); ax.set_ylabel("Relative to the best $K^*$ (%)")
        ax.set_xticks([1, 2, 3, 4, 5, 6])
        if t == cfgs[0]:
            ax.legend(fontsize=8.5, loc="upper left")
    fig.tight_layout()
    save(fig, "fig04_cost_vs_K.png")


def fig5():
    sc = D["scan_cost"]
    x = np.arange(len(sc["cfg"]))
    fig, ax = plt.subplots(figsize=(8.8, 4.3))
    ax.bar(x - 0.2, sc["solve"], 0.4, color=C_SAFE, label="Reference run (historical summary)")
    ax.bar(x + 0.2, sc["scan"], 0.4, color=C_DANGER, label="One period-grid scan (5 levels × 3 rounds)")
    ax.set_yscale("log")
    for i, r in enumerate(sc["ratio"]):
        ax.text(i + 0.2, sc["scan"][i] * 1.18, "%.1f×" % r, ha="center",
                fontsize=10, color=C_DANGER, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(sc["cfg"])
    ax.set_ylabel("Wall-clock time (s, log scale)")
    ax.legend(fontsize=9.5); ax.set_ylim(5, 9000)
    save(fig, "fig05_scan_cost.png")


def fig6():
    kr = D["kstar_rounds"]; cfgs = kr["cfg"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.8, 4.5),
                                   gridspec_kw={"width_ratios": [1.1, 1]})
    kmap = {"K1": 1, "K2": 2, "K3": 3, "K4": 4, "K5": 5, "K6": 6}
    x = np.arange(len(cfgs)); w = 0.26
    for j, (r, col) in enumerate(zip(["r1", "r2", "r3"], [C_NEUT, C_WARN, C_DANGER])):
        ys = [kmap[kr[r][i]] for i in range(len(cfgs))]
        ax1.bar(x + (j - 1) * w, ys, w, color=col, label="Round %d" % (j + 1))
    ax1.set_xticks(x); ax1.set_xticklabels(cfgs)
    ax1.set_ylabel("Best $K$ obtained in that round")
    ax1.set_yticks([1, 2, 3, 4, 5]); ax1.set_yticklabels(["K1", "K2", "K3", "K4", "K5"])
    ax1.set_ylim(0, 6.6)
    ax1.set_title("(a) $K^*$ taken per round: inconsistent on 5/5 configurations", fontsize=11.5)
    ax1.legend(fontsize=9, ncol=3, loc="upper center", framealpha=0.9)
    ax2.axis("off")
    txt = ("Merging by median makes $K_5$ win only because its median is slightly lower;\n"
           "round by round the winner flips freely among K3/K4/K5.\n\n"
           "Closest round (a tie):\n"
           "  · fine round 2: K4 167811 vs K5 167865\n"
           "    → difference 54 ms (a computation of minutes) = 0.03%\n"
           "  · x3  round 2: K3 670003 vs K4 670228\n"
           "    → difference 225 ms = 0.03%\n\n"
           "⇒ This is a tie, not an optimum.\n\n"
           "The disadvantage of $K=1$, by contrast, is robust:\n"
           "  18 of 20 round-paired comparisons agree across all rounds (90%)")
    ax2.text(0.02, 0.97, txt, transform=ax2.transAxes, fontsize=10.2, va="top",
             ha="left", linespacing=1.6,
             bbox=dict(boxstyle="round,pad=0.6", fc="#f7f7f7", ec="#bbb"))
    fig.tight_layout()
    save(fig, "fig06_kstar_unidentifiable.png")


def fig7():
    onl = D["online"]; cfgs = ALL7
    gap = [100 * (onl[t]["onl"] / onl[t]["fix"] - 1) for t in cfgs]
    save1 = [100 * (onl[t]["onl"] / onl[t]["K1"] - 1) for t in cfgs]
    x = np.arange(len(cfgs)); w = 0.38
    fig, ax = plt.subplots(figsize=(10.0, 4.6))
    ax.bar(x - w / 2, gap, w, color=C_MAIN, label="Gap to the best fixed period $K^*$ in hindsight (positive = worse)")
    ax.bar(x + w / 2, save1, w, color=C_BEST, label="Relative to $K=1$, rebuild every step (negative = cheaper)")
    ax.axhline(0, color="#333", lw=1.1)
    for i in range(len(cfgs)):
        ax.text(i - w / 2, gap[i] + 0.5, "%+.1f%%" % gap[i], ha="center",
                fontsize=9.5, color=C_MAIN, fontweight="bold")
        ax.text(i + w / 2, save1[i] - 1.0, "%.1f%%" % save1[i], ha="center", va="top",
                fontsize=9, color=C_BEST)
    labs = []
    for t in cfgs:
        lab = "primary" if t in MAIN else ("supporting" if t in SIDE else "boundary")
        col = C_MAIN if t in MAIN else (C_WARN if t in SIDE else "#888")
        labs.append((lab, col))
    ax.set_xticks(x)
    ax.set_xticklabels(cfgs)
    for i, (lab, col) in enumerate(labs):
        ax.annotate(lab, xy=(i, 0), xycoords=("data", "axes fraction"),
                    xytext=(0, -34), textcoords="offset points",
                    ha="center", fontsize=8.5, color=col, fontweight="bold")
    ax.set_ylabel("Relative difference (%)"); ax.set_ylim(-44, 9)
    fig.subplots_adjust(bottom=0.24, top=0.84)
    ax.legend(fontsize=9.5, loc="lower center", bbox_to_anchor=(0.5, 1.01),
              ncol=2, frameon=False)
    save(fig, "fig07_online_performance.png")


def fig8():
    cfgs = ["l20", "fl30", "fx", "l15", "x3"]
    fig, axes = plt.subplots(len(cfgs), 1, figsize=(12, 6.8))
    for ax, t in zip(axes, cfgs):
        v = D["fig8"][t]
        ax.imshow(np.array([v["model"], v["cpp"]]), aspect="auto", cmap="Blues", vmin=0, vmax=1, extent=[1, v["n"], 0, 2], interpolation="nearest")
        ax.set_yticks([.5, 1.5]); ax.set_yticklabels(["C++", "model"], fontsize=8)
        ax.set_ylabel(t); ax.grid(False)
    axes[-1].set_xlabel("Time step (dark = rebuild)")
    fig.tight_layout(); save(fig, "fig08_decision_sequence.png")


def fig9():
    de = D["delta_end"]; cfgs = de["cfg"]
    fig, ax = plt.subplots(figsize=(9.0, 4.4))
    cols = [C_MAIN if i else C_DANGER for i in de["in_scope"]]
    ax.scatter(range(len(cfgs)), de["rate"], s=170, c=cols, zorder=4,
               edgecolor="white", lw=1.4)
    for i, r in enumerate(de["rate"]):
        dy = -19 if i == len(de["rate"]) - 1 else 11
        ax.annotate("%.1f%%" % r, (i, r), textcoords="offset points",
                    xytext=(0, dy), ha="center", fontsize=9.5)
    ax.annotate("sth: ageing saturates after $a\\approx6$\nboundary diagnostic only\nnot a sufficient inclusion criterion",
                xy=(6, 5.6), xytext=(3.0, 20), fontsize=10, color=C_DANGER,
                ha="center", va="center",
                arrowprops=dict(arrowstyle="->", color=C_DANGER, lw=1.2),
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=C_DANGER, alpha=0.92))
    ax.set_xticks(range(len(cfgs))); ax.set_xticklabels(cfgs)
    ax.set_ylabel("Local relative increment at $t=200$, ages 5→6 (%)"); ax.set_ylim(0, 66)
    save(fig, "fig09_scope_criterion.png")


def fig10():
    onl = D["online"]
    fig, ax = plt.subplots(figsize=(9.2, 4.3))
    for i, t in enumerate(ALL7):
        r1 = onl[t]["rho"]; s = onl[t]["s"]
        ax.plot([r1, r1 * s], [i, i], lw=7, color=C_NEUT, alpha=0.55, solid_capstyle="round")
        ax.plot([r1], [i], "o", color=C_MAIN, ms=7, zorder=4)
        ax.plot([r1 * s], [i], "D", color=C_WARN, ms=6, zorder=4)
        ax.text(r1 * 0.88, i, "%.0f" % r1, fontsize=8.5, va="center", ha="right", color=C_MAIN)
        ax.text(r1 * s * 1.05, i, "s=%.2f" % s, fontsize=8, va="center", color="#777")
    ax.set_yticks(range(len(ALL7))); ax.set_yticklabels(ALL7)
    ax.set_xlabel("Rebuild cost ratio $\\rho$"); ax.set_xscale("log"); ax.set_xlim(9, 1200)
    ax.plot([], [], "o-", color=C_MAIN, label="Lower bound $r_1$ (one rebuild charged as 1 factorisation)")
    ax.plot([], [], "D-", color=C_WARN, label="Upper bound $s\\,r_1$ (charged as $s$ factorisations)")
    ax.legend(fontsize=9.5, loc="lower right")
    save(fig, "fig10_rho_interval.png")


def fig11():
    H = D["heur"]; cfgs = ALL7
    names = [("onl", "Online (this paper)", C_MAIN), ("ch", "Chalmers", C_DANGER),
             ("re", "REAC(120)", C_WARN), ("ra", "20% rule", C_LIGHT)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.4, 4.6), sharey=True)
    for ax, mode, ttl in [(ax1, "r1", "$\\rho=r_1$"), (ax2, "sr1", "$\\rho=s\\,r_1$")]:
        x = np.arange(len(cfgs)); w = 0.2
        for j, (key, lab, col) in enumerate(names):
            ys = [100 * (H[mode][t][key] / H[mode][t]["orc"] - 1) for t in cfgs]
            ax.bar(x + (j - 1.5) * w, ys, w, color=col, label=lab)
        ax.set_xticks(x); ax.set_xticklabels(cfgs, fontsize=9.5)
        ax.axhline(0, color="#333", lw=1.0)
        ax.set_title(ttl, fontsize=12)
        ax.set_yscale("symlog", linthresh=10); ax.set_ylim(-5, 400)
    ax1.set_ylabel("regret (relative to the DP oracle, %, symlog)")
    ax1.text(0.03, 0.97, "Online beats Chalmers 2/7,\nloses 5/7 (0.31%–5.79% higher cost)",
             transform=ax1.transAxes, fontsize=9.5, color=C_DANGER, va="top",
             bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=C_DANGER, alpha=0.92))
    ax2.text(0.03, 0.97, "Online beats Chalmers 6/7\n(ordering reverses with $\\rho$)",
             transform=ax2.transAxes, fontsize=9.5, color=C_BEST, va="top",
             bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=C_BEST, alpha=0.92))
    h, l = ax1.get_legend_handles_labels()
    fig.legend(h, l, fontsize=9, ncol=4, loc="upper center",
               bbox_to_anchor=(0.5, 1.0), frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    save(fig, "fig11_heuristic_comparison.png")


def fig12():
    onl = D["online"]; cfgs = ALL7
    exp = [100 * (onl[t]["onl"] - D["heur"]["r1"][t]["pf"]) / D["heur"]["r1"][t]["pf"]
           for t in cfgs]
    gap = [100 * (onl[t]["onl"] / onl[t]["fix"] - 1) for t in cfgs]
    x = np.arange(len(cfgs)); w = 0.38
    fig, ax = plt.subplots(figsize=(10.0, 4.5))
    ax.bar(x - w / 2, gap, w, color=C_MAIN, label="Gap to the best fixed period $K^*$ in hindsight")
    ax.bar(x + w / 2, exp, w, color=C_WARN, label="Online learning cost (online − perfect belief)")
    for i in range(len(cfgs)):
        ax.text(i - w / 2, gap[i] + 0.12, "%+.2f" % gap[i], ha="center",
                fontsize=9, color=C_MAIN)
        ax.text(i + w / 2, exp[i] + 0.12, "%+.2f" % exp[i], ha="center",
                fontsize=9, color=C_WARN)
    ax.set_xticks(x); ax.set_xticklabels(cfgs)
    ax.set_ylabel("Relative difference (%)"); ax.set_ylim(0, 8.8)
    ax.legend(fontsize=9.5, loc="upper left")
    save(fig, "fig12_calibration_cost.png")


def fig13():
    onl = D["online"]; H = D["heur"]["r1"]; cfgs = ALL7
    exp = [100 * (onl[t]["onl"] - H[t]["pf"]) / H[t]["orc"] for t in cfgs]
    dch = [100 * (onl[t]["onl"] - H[t]["ch"]) / H[t]["orc"] for t in cfgs]
    resid = [100 * (H[t]["pf"] - H[t]["ch"]) / H[t]["orc"] for t in cfgs]
    exp = np.array(exp); dch = np.array(dch); resid = np.array(resid)
    x = np.arange(len(cfgs)); w = 0.26
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.6),
                                  gridspec_kw={"width_ratios": [1.45, 1]})
    ax.bar(x - w, dch, w, color=C_DANGER, label="Gap to Chalmers (online − Chalmers)")
    ax.bar(x, exp, w, color=C_WARN, label="Online learning cost (online − perfect belief)")
    ax.bar(x + w, resid, w, color=C_BEST, label="Residual gap of perfect belief (perfect belief − Chalmers)")
    ax.axhline(0, color="#333", lw=1.0)
    ax.annotate("Learning cost > gap\n(5/5 configurations lost)", xy=(1.28, 5.0), xytext=(2.0, 9.1),
                fontsize=10, color="#444", ha="center", va="top",
                arrowprops=dict(arrowstyle="->", color="#444", lw=1.1),
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#888", alpha=0.95))
    ax.set_xticks(x); ax.set_xticklabels(cfgs)
    ax.set_ylabel("Cost difference / DP (percentage points)"); ax.set_ylim(-6.5, 9.2)
    ax.set_title("(a) Three-bar comparison per configuration", fontsize=11.5)
    ax.legend(fontsize=8.6, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.14),
              frameon=False)
    ax2.scatter(dch[dch > 0], exp[dch > 0], s=110, c=C_DANGER, zorder=4, edgecolor="white",
                lw=1.2, label="Lost by this paper (5)")
    ax2.scatter(dch[dch <= 0], exp[dch <= 0], s=120, c=C_BEST, zorder=4, marker="^",
                edgecolor="white", lw=1.2, label="Won by this paper (2)")
    lim = np.linspace(-6, 9, 50)
    ax2.plot(lim, lim, "--", color="#888", lw=1.5, label="$y=x$")
    ax2.fill_between(lim, lim, 9.2, color=C_WARN, alpha=0.10)
    ax2.text(8.5, 8.9, "In this region learning cost > gap.\nAblation only; does not identify\nthe whole causal origin",
             fontsize=9, color="#8a5a00", ha="right", va="top")
    off = {"fx": (8, 6), "l15": (8, 4), "l20": (8, 4), "x3": (8, 4),
           "fine": (8, -12), "fl30": (10, -13), "sth": (-12, 5)}
    for i, t in enumerate(cfgs):
        ax2.annotate(t, (dch[i], exp[i]), textcoords="offset points",
                     xytext=off.get(t, (8, 4)), fontsize=8.5)
    ax2.set_xlabel("Difference to Chalmers / DP (percentage points)"); ax2.set_ylabel("Learning-ablation difference / DP (percentage points)")
    ax2.set_xlim(-6.5, 9); ax2.set_ylim(-0.2, 9.2)
    ax2.set_title("(b) 5/5 fall above the diagonal", fontsize=11.5)
    ax2.legend(fontsize=8.6, loc="lower right")
    fig.tight_layout()
    save(fig, "fig13_attribution.png")


def fig14():
    H = D["heur"]["r1"]; cfgs = ALL7
    pfk = [100 * (H[t]["pf"] / H[t]["fix"] - 1) for t in cfgs]
    pfch2 = [100 * (H[t]["pf"] / H[t]["ch"] - 1) for t in cfgs]
    pfch = [100 * (H[t]["pf"] / H[t]["cs"] - 1) for t in cfgs]
    x = np.arange(len(cfgs)); w = 0.26
    fig, ax = plt.subplots(figsize=(10.2, 4.5))
    ax.bar(x - w, pfk, w, color=C_BEST, label="vs best fixed period $K^*$ in hindsight")
    ax.bar(x, pfch2, w, color=C_DANGER, label="vs Chalmers (original constant 2.0)")
    ax.bar(x + w, pfch, w, color=C_WARN, label="vs Chalmers (per-configuration oracle constant $f^*$)")
    ax.axhline(0, color="#333", lw=1.2)
    for i in range(len(cfgs)):
        for off, val, col in [(-w, pfk[i], C_BEST), (0, pfch2[i], C_DANGER),
                              (w, pfch[i], C_WARN)]:
            ax.text(i + off, val - 0.18, "%.2f" % val, ha="center", fontsize=8.6,
                    va="top", color=col)
    ax.set_xticks(x); ax.set_xticklabels(cfgs)
    ax.set_ylabel("Relative difference (%, negative = perfect belief better)"); ax.set_ylim(-8.8, 1.4)
    ax.legend(fontsize=9, loc="lower left")
    save(fig, "fig14_perfect_belief.png")


def fig15():
    S = D["sens"]; cfgs = ALL7
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.4, 4.5))
    cmap = plt.get_cmap("tab10")
    for i, t in enumerate(cfgs):
        ax1.plot(S["fac"], S["ch"][t], "o-", ms=4, lw=1.6, color=cmap(i % 10), label=t)
        fs = D["heur"]["r1"][t]["fs"]
        j = S["fac"].index(fs)
        ax1.plot([fs], [S["ch"][t][j]], "*", ms=15, color=cmap(i % 10),
                 markeredgecolor="white", zorder=5)
    ax1.axvline(2.0, color=C_DANGER, ls="--", lw=1.8)
    ax1.text(2.08, 74, "Hard-coded $f=2.0$ of the original paper\n(optimal for none of the configurations)",
             color=C_DANGER, fontsize=9.5, va="top", fontweight="bold")
    ax1.set_xlabel("Chalmers threshold constant $f$"); ax1.set_ylabel("regret vs oracle (%)")
    ax1.set_ylim(-3, 98); ax1.set_xscale("log")
    ax1.set_xticks([1.05, 1.5, 2, 3, 4, 6, 10])
    ax1.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax1.set_title("(a) Stars = each configuration’s best $f^*$ in hindsight", fontsize=11.5)
    ax1.legend(fontsize=8.2, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.20), frameon=False)
    for i, t in enumerate(cfgs):
        ax2.plot(S["reac"], S["re"][t], "o-", ms=4, lw=1.6, color=cmap(i % 10), label=t)
        rs = D["heur"]["r1"][t]["restar"]
        if rs in S["reac"]:
            j = S["reac"].index(rs)
            ax2.plot([rs], [S["re"][t][j]], "*", ms=15, color=cmap(i % 10),
                     markeredgecolor="white", zorder=5)
    ax2.axvline(120, color=C_DANGER, ls="--", lw=1.8)
    ax2.text(128, 55, "We fix 120 throughout", color=C_DANGER, fontsize=9.5, fontweight="bold",
             ha="left", va="center",
             bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))
    ax2.axvspan(40, 60, color=C_BEST, alpha=0.13)
    ax2.text(50, 1.55, "Optimal thresholds in the narrow band 40–60", color=C_BEST, fontsize=9.5, ha="center",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=C_BEST, alpha=0.92))
    ax2.set_xlabel("REAC threshold"); ax2.set_ylabel("regret vs oracle (%)")
    ax2.set_yscale("symlog", linthresh=1); ax2.set_ylim(-0.6, 400)
    ax2.set_title("(b) REAC’s optimal threshold falls in 40–60 (sth outside)", fontsize=11.5)
    ax2.legend(fontsize=8.2, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.20), frameon=False)
    fig.tight_layout()
    save(fig, "fig15_sensitivity.png")


def fig16():
    fig, axes = plt.subplots(2, 2, figsize=(13, 5.8), gridspec_kw={"height_ratios": [1, 1.2]})
    for col, t in enumerate(["fine", "sth"]):
        v, bb = D["fig8"][t], D["boundary"][t]
        model, cpp = np.array(v["model"]), np.array(v["cpp"])
        assert len(model) == len(cpp) == v["n"]
        first = int(np.flatnonzero(model != cpp)[0]) + 1
        for row, (lo, hi) in enumerate([(1, v["n"]), (244, 272) if t == "fine" else (98, 154)]):
            ax = axes[row, col]
            ax.imshow(np.array([model[lo-1:hi], cpp[lo-1:hi]]), aspect="auto", cmap="Blues", vmin=0, vmax=1, extent=[lo-.5, hi+.5, 0, 2], interpolation="nearest")
            ax.set_yticks([.5, 1.5]); ax.set_yticklabels(["C++ measured", "model"]); ax.grid(False)
            ax.axvline(first, color=C_DANGER, ls="--", lw=1)
            ax.set_xlabel("Time step $t$ (dark = rebuild)")
            if row == 0:
                ax.set_title("%s: agreement %.2f%%; same-table pricing difference %.2f%%" % (t, v["agree"], bb["price_diff"]), fontsize=11)
            else:
                ax.set_title("Raw action sequence, detail: t=%d–%d" % (lo, hi), fontsize=11)
    fig.tight_layout(); save(fig, "fig16_agreement_misleading.png")


if __name__ == "__main__":
    print("Figures written to", OUT)
    funcs = [fig1, fig2, fig3, fig4, fig5, fig6, fig7, fig8,
             fig9, fig10, fig11, fig12, fig13, fig14, fig15, fig16]
    bad = 0
    for fn in funcs:
        try:
            fn()
        except Exception as e:
            import traceback; bad += 1
            print("  !! %s failed: %s" % (fn.__name__, e)); traceback.print_exc()
    print("done, %d failed" % bad)
