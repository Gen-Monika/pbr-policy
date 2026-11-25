#!/usr/bin/env python3
"""Recompute pressure-module cost from wd* pc CSVs (same formula as seven-config doc).

Formula (per run, over all rows with field=p_rgh):
    sum(tConvert) + sum(tPCSetup) + tApplyAccum(final) + median(ma over measured rows) * nApplyCalls(final)

Columns (1-indexed) per PETScPreconditioner.C CSV write:
 1 timeIndex, 2 fieldTag, 3 kind, 4 levels, 5 nCells, 6 nFaces, 7 rep,
 8 freezeAt, 9 reused, 10 period, 11 reusedFrom, 12 adopted, 13 tFreeze,
 14 tConvert, 15 tPCSetup, 16 tAssemble, 17 ma, 18 mp, 19 tIter,
 20 r, 21 rTotal, 22 tApplyAccum, 23 nApplyCalls,
 24 tSetupAll, 25 nBuildPC
"""
import glob, os, re, statistics, sys

def parse(path):
    s_conv = s_setup = 0.0
    mas, last, nrows = [], None, 0
    with open(path) as f:
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) < 25:
                continue
            if p[1].strip() != "p_rgh":
                continue
            nrows += 1
            s_conv += float(p[13])
            s_setup += float(p[14])
            ma = float(p[16])
            if ma >= 0:
                mas.append(ma)
            last = p
    if last is None:
        return None
    ta, nc = float(last[21]), float(last[22])
    tsetup_all = float(last[23])
    ma_med = statistics.median(mas) if mas else 0.0
    return dict(rows=nrows, conv=s_conv, setup=s_setup, tapply=ta, ncalls=nc,
                ma_med=ma_med, total=s_conv + s_setup + ta + ma_med * nc,
                tsetup_all=tsetup_all, dsum=abs(s_setup - tsetup_all))

def main(d):
    files = sorted(glob.glob(os.path.join(d, "wd*_pc_*.csv")))
    rows = []
    for f in files:
        m = re.match(r"wd(.+?)r(\d)_pc_(\w+)_r\d+\.csv$", os.path.basename(f))
        if not m:
            print("UNMATCHED", f); continue
        cfg, rnd, mode = m.group(1), int(m.group(2)), m.group(3)
        r = parse(f)
        if r is None:
            print("EMPTY", f); continue
        r.update(cfg=cfg, rnd=rnd, mode=mode)
        rows.append(r)

    print("cfg  rnd mode   total    conv    setup   tapply   ncalls  ma_med   |setup-all|")
    for r in sorted(rows, key=lambda x: (x["cfg"], x["rnd"], x["mode"])):
        print(f"{r['cfg']:5s} {r['rnd']}  {r['mode']:5s} {r['total']:8.4f} {r['conv']:7.4f} "
              f"{r['setup']:7.4f} {r['tapply']:7.4f} {r['ncalls']:8.0f} {r['ma_med']:.6f} {r['dsum']:.2e}")

    idx = {(r["cfg"], r["rnd"], r["mode"]): r for r in rows}
    cfgs = sorted({r["cfg"] for r in rows})
    print("\n=== paired ratios K1/mode ===")
    print("cfg  mode  ratio_of_med  save_of_med%  paired_med_ratio  paired_med_save%   per-round saves")
    for cfg in cfgs:
        rounds = sorted({r["rnd"] for r in rows if r["cfg"] == cfg})
        for mode in ("K3", "ONLp"):
            ratios = []
            for rn in rounds:
                k1, mo = idx.get((cfg, rn, "K1")), idx.get((cfg, rn, mode))
                if k1 and mo:
                    ratios.append(k1["total"] / mo["total"])
            if not ratios: continue
            k1s = [idx[(cfg, rn, "K1")]["total"] for rn in rounds if (cfg, rn, "K1") in idx]
            mos = [idx[(cfg, rn, mode)]["total"] for rn in rounds if (cfg, rn, mode) in idx]
            rom, momed = statistics.median(k1s), statistics.median(mos)
            rs = " ".join(f"{(1-1/q)*100:.1f}" for q in ratios)
            print(f"{cfg:5s} {mode:5s} {rom/momed:12.4f} {(1-momed/rom)*100:12.2f} "
                  f"{statistics.median(ratios):17.4f} {statistics.median([(1-1/q)*100 for q in ratios]):16.2f}   [{rs}]")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
