# Data

Measured records behind the figures. Nothing here is simulated or smoothed: every
file is solver output or a parsed record of it.

This directory is **optional**. Cloning the whole repository pulls about 200 MB,
almost all of it here. If you only want the code, see "Cloning without the data"
in the repository README.

## `phase/` — the cost tables the policy is evaluated on

49 comma-separated decision records and 49 solver logs, covering seven cases at
seven rebuild-period anchors each:

| Case | Levels | Steps `T` | Anchor `B` |
|---|---|---|---|
| `fx` | 10 | 344 | 94–100 |
| `l15` | 15 | 344 | 94–100 |
| `l20` | 20 | 344 | 94–100 |
| `fine` | 20 | 720 | 94–100 |
| `x3` | 20 | 1231 | 94–100 |
| `fl30` | 30 | 720 | 94–100 |
| `sth` | 5 | 5866 | 44–50 |

File names are `phs_<case>_B<anchor>_K7_r1.csv`, with the matching solver log at
`phs_<case>/log.B<anchor>K7_r1`. `K7` denotes the seven ageing bins. The `sth`
anchor is 50 rather than 100; this is what `PHASE_B0_SCAN` in
`../code/pbrPETSc/pbrcost.py` encodes, and it is deliberate rather than an
oversight.

`pbrcost.load_phase` reads both halves: the CSV supplies the setup-to-iteration
ratios and the reuse/freeze decisions, the log supplies the per-step iteration
counts and the number of pressure solves per step. A missing log means the
anchor is skipped, so both files are needed for every anchor.

## `traces/` — what the C++ runs actually did

69 decision records covering the same seven cases over their measured rounds:

- `a2<case>_pc_ONLs_<round>.csv` — paired per-step record, the one used for the
  figures;
- `a2<case>_sv_ONLs_<round>.csv` and `a2<case>_onl_ONLs_<round>.csv` — the two
  arms the paired record is derived from.

Each row is one solve of one step. Rows with `rep < 0` are rejected attempts and
are skipped when decoding. The rebuild decision is `reusedFrom < 0`; the
alternative reading `freezeAt == 0` gives a different sequence and does **not**
reproduce the published numbers.

## `alt_cases/`, `fine_grid/`, `levels_trend/`, `night_2026-10-11/`, `s_lever/`

Scan outputs from the supporting experiments (alternative physical cases, grid
refinement, level trends, one overnight batch, the sensitivity study). They are
plain text from the scan driver.

## Reproducing the agreement rates of Fig. 8

```bash
python3 code/figs/build_model_decisions.py
```

This rebuilds the model-side sequences from `data/phase/`, decodes the C++ side
from `data/traces/`, and prints the agreement rate per case. You should get
100.00% for `l20`, `fl30`, `fx`, `l15` and `x3`, 34.31% for `fine` and 73.70% for
`sth`. Those are the numbers in the paper; the low `fine` value is the point of
that panel, not a defect.

## Provenance

Pulled from the run host on 2026-11-25 and copied here unchanged. The archives
they came from, for integrity checking:

```
pbr_traces_20261125.tar.gz  c90601c28db93e14110b29baa86f7f07d8f648ae68326cedf1035722026a670d
pbr_phase_20261125.tar.gz   ab7b84c093585d265f15ff860a0fffb2f0bd28f3e02185037e6cc5ab06ca1e6d
```

The solver logs are raw and unedited, which is why they dominate the size. They
were kept in full rather than trimmed to the lines the parser reads, so that the
records can be checked against the runs themselves.
