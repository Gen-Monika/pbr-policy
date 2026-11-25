#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the model-side decision sequences and the agreement rates of Fig. 8.

Fig. 8 compares two decision sequences for each case:

  model  -- produced by the online policy evaluated on the measured cost tables
            (``pbrcost.load_phase`` -> ``sim_online_detail``)
  cpp    -- the decisions actually taken in the C++ run, read back from the
            per-case decision records in ``data/traces/``

The two conventions that reproduce the published numbers, and that are easy to
get wrong, are:

  * ``rho = r1`` -- the rebuild cost ratio taken as the measured lower bound,
    NOT ``s * r1``.  Using ``s * r1`` shifts every sequence and drops the
    agreement rate from 100% to roughly 65% on the linear cases.
  * ``step_cost=False`` -- the per-solve accounting of ``sim_online_detail``,
    matching the ``ONLs`` column convention of the traces.

Usage::

    python3 code/figs/build_model_decisions.py            # print a table
    python3 code/figs/build_model_decisions.py --json out.json

The phase-scan tables read here are under ``data/phase/``; the per-case
decision records are under ``data/traces/``.  Both were produced by the runs
described in the paper and are shipped unchanged.
"""
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# Fig. 8 subplot -> (case tag in pbrcost, decision record in data/traces/)
CASES = [
    ("l20", "l20", "a2A_pc_ONLs_r1.csv"),
    ("fl30", "fl30", "a2B_pc_ONLs_r1.csv"),
    ("fx", "fx", "a2fx_pc_ONLs_r1.csv"),
    ("l15", "l15", "a2l15_pc_ONLs_r1.csv"),
    ("x3", "x3", "a2x3_pc_ONLs_r1.csv"),
    ("fine", "fine", "a2fine_pc_ONLs_r1.csv"),
    ("sth", "sth", "sthB100a_pc_ONLs_r1.csv"),
]

TRAIL = ("timeIndex,field,kind,levels,nCells,nFaces,rep,freezeAt,reused,period,"
         "reusedFrom,adopted,tFreeze,tConvert,tPCSetup,tAssemble,ma,mp,tIter,"
         "r,rTotal,tApplyAccum,nApplyCalls,tSetupAll,nBuildPC").split(",")


def load_pbrcost():
    """Import pbrcost and point its data root at this repository."""
    path = os.path.join(ROOT, "code", "pbrPETSc", "pbrcost.py")
    spec = importlib.util.spec_from_file_location("pbrcost", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.P2 = os.path.join(ROOT, "data", "phase")
    return mod


def cpp_decisions(path):
    """Rebuild iff ``reusedFrom < 0``, on the first valid row of each step."""
    idx = {k: i for i, k in enumerate(TRAIL)}
    seen = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != len(TRAIL):
                continue
            if int(parts[idx["rep"]]) < 0:
                continue
            t = int(parts[idx["timeIndex"]])
            if t not in seen:
                seen[t] = parts
    steps = sorted(seen)
    return [1 if int(seen[t][idx["reusedFrom"]]) < 0 else 0 for t in steps]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", metavar="PATH", help="write the sequences here")
    args = ap.parse_args()

    pc = load_pbrcost()
    out = {}
    print(f"{'case':<6}{'steps':>7}{'model rebuilds':>16}{'cpp rebuilds':>14}"
          f"{'agree':>9}")
    print("-" * 54)
    for fig_tag, tag, record in CASES:
        data = pc.load_phase(tag)
        if data is None:
            print(f"{fig_tag:<6}{'load_phase returned None':>44}")
            continue
        lvl, T, B0 = pc.CFG[tag]
        env = pc.Env(data["tab"], sFact=data["s"])
        _, _, n_rebuild, pred, _ = pc.sim_online_detail(
            env, data["r1"], T, B0, step_cost=False)
        model = [int(x) for x in pred]
        cpp = cpp_decisions(os.path.join(ROOT, "data", "traces", record))
        n = min(len(model), len(cpp))
        agree = sum(1 for i in range(n) if model[i] == cpp[i])
        pct = 100.0 * agree / n if n else float("nan")
        out[fig_tag] = {
            "n": n,
            "model": model,
            "cpp": cpp,
            "n_dif": n - agree,
            "agree": pct,
            "src": record,
            "rho": data["r1"],
            "B0": B0,
        }
        print(f"{fig_tag:<6}{n:>7}{sum(model):>16}{sum(cpp):>14}{pct:>8.2f}%")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
        print(f"\nwritten {args.json}")


if __name__ == "__main__":
    main()
