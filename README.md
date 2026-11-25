# PBR — Calibration-free preconditioner rebuild scheduling

Preconditioners in transient simulations go stale as the operator drifts. PBR decides
*when to rebuild* them online, from runtime measurements only: it tracks the
setup-to-iteration cost ratio and estimates operator aging increments on the fly, using the
running average cost per solve as a dynamic rebuild threshold. No offline calibration,
no pre-training and no manual parameters are required, and the policy transfers across
solvers.

This repository contains the policy implementations, the measured data behind the figures,
the formal verification certificate and the reproduction entry points.

## Contents

| Path | What it is |
|---|---|
| `code/` | Policy modules for the five hosts: header-only C++ for OpenFOAM/PETSc, ASPECT and MOOSE; a Fortran module for Elmer/Ice; a patch for LaMEM. Also the figure scripts (`code/figs/`) and the timing analysis (`code/wallclock_analysis/`). |
| `data/` | Measured records: the phase-scan cost tables and their solver logs (`data/phase/`), the per-case decision traces of the C++ runs (`data/traces/`), and scan outputs of the supporting experiments. See `data/README.md`. |
| `proof/` | Lean 4 certificate for the convergence claims in the theoretical section, with the verification record. |
| `reproduce/` | Build and run paths for all five hosts, case inputs and reference values. |

## Repository size, and cloning without the data

The full clone is about 200 MB, of which roughly 180 MB is `data/`: the measured
records plus the raw solver logs they were parsed from. That data is what makes
the figures checkable, but you do not need it to read, build or use the policy.

Take only the code if that is what you want:

```bash
git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/Gen-Monika/pbr-policy.git
cd pbr-policy
git sparse-checkout set code reproduce proof
```

Add `data` to the sparse set later with `git sparse-checkout add data`, or pull
individual files from the web interface. The choice is deliberately yours: the
records are shipped in full rather than summarised, so the repository is heavier
than a code-only release would be.

## Requirements

Linux, Bash 4 or newer, Python 3.8 or newer, and a compiler toolchain plus MPI matching
whatever the host solver is actually linked against. Each host must be installed by the
user beforehand; see `LICENSE-NOTES.md` for how this repository relates to the host
licences.

Suggested host versions (ours, not hard requirements): OpenFOAM v2406 with PETSc 3.25.1,
MOOSE with Open MPI 5.0.10, LaMEM 3.3.0, ASPECT 2.4.0 with deal.II 9.3.2 and Trilinos
13.2.0, Elmer/Ice 26.2 with `WITH_MPI=TRUE`.

## Quick start

The lowest-friction entry is the serial fixed-period validation on OpenFOAM. Point the
scripts at your installation in `reproduce/config/site.local.sh` (a template is provided),
then build and run:

```bash
bash reproduce/scripts/verify_environment.sh
bash reproduce/scripts/build_openfoam.sh --help
```

`reproduce/README.md` is the authoritative step-by-step guide: configuration precedence,
per-host environment keys, the five build/run paths, and the meaning of the reference
values in `reproduce/expected/`. That guide is currently written in Chinese; an English
translation is pending.

## Scope of the claims

The Lean certificate covers the idealised stationary model stated in the paper, not the
production code paths. The empirical results are three-round comparisons on the official
benchmarks of ASPECT and Elmer/Ice plus the four-host cost study; they are not a proof that
the mechanism is causal in every deployment.

## Known limitations

Two of the five host entries do not reach their reference precision in a single run: the
Elmer/Ice entry at `np=8` misses the tolerance, and the LaMEM entry does not complete all
rounds. These are documented in `reproduce/README.md` rather than suppressed, and
`reproduce/expected/` is not adjusted to hide them. Counting agreement, run completion and
reference precision are three independent results; please do not tune solver settings or
tolerances to match the recorded numbers.

## Licence

BSD 3-Clause; see `LICENSE`. Third-party hosts are **not** redistributed. `LICENSE-NOTES.md`
explains how the separable modules relate to the GPL-family host licences.

## Citing

The accompanying paper is under review. Until it appears, please cite this repository by
its URL. A DOI will be added once the archived release exists.

## Funding

This work is supported by the Research Fund of National Key Laboratory of Aerospace Physics
in Fluids (Grant No. 2025-APF-KFZD-30).

## Contact

Fei Ye — `32956424u@gmail.com`
Yin Long (corresponding author) — `yinnuoloong@163.com`
