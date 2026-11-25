# Phase-index experiment (2026-10-17)

`PBR_COND=index` enables conditioning only for `PBR_POLICY=online`, `PBR_UNIT=solve`.
Default/unset/off retains the server's original policy, including its matrix-reset protection.

The existing warm-up (`solve index < PBR_BASE`) supplies age-zero, positive-iteration
samples. At its end, compute the same upper median as the legacy code for each j,
then freeze `q[j]=median(N|j,age=0)-median(N|j=0,age=0)` until a mesh reset.
No new fitted tolerance, window or tunable parameter is introduced. Missing j,
including those first appearing later, uses q=0. If j=0 has no samples, all offsets
are zero. This fallback leaves that sample unadjusted; it is not a claim that the
entire policy state equals a separate unconditioned run.

Re-express warm-up levels/total once in the frozen coordinate. All later levels,
age residuals, latest-rebuild prediction and running cost use `M=N-q[j]`.
Raw N remains the eligibility check (legacy ignores zero-N observations), the rho
measurement and the reported physical cost. M is signed double; negative M is not
clipped. Frozen offsets deliberately do not track time drift. Unknown-phase
observations enter the same model with q=0, an explicit limitation to report.

With j identically zero, every q is exactly zero; no re-expression occurs, and
every legacy operation/state value remains identical on the same observation stream.
The original timing-based rho may differ between independent physical runs.

`replay.cpp` includes both the preserved server header and the new header and checks
exact decisions and internal state on six existing recorded streams, in off and
all-zero-j modes. Missing zero/terminal rows in historical CSV are not reconstructed;
these are compatibility replays, not counterfactual solver experiments. Separate
behavioral checks cover no-aging phases, signed model values, missing anchors,
frozen offsets, raw rho, and mesh reset.

The incremental `aspect_phase_index.diff` and `moose_phase_index.diff` apply on top
of the current patched server sources. ASPECT's original tree is unchanged: an
isolated source copy feeds `envs/aspect-2.4/build-pbr3`. MOOSE's library and source
backups are stored with the server experiment before rebuilding.

Experiment scripts are preserved in `experiments/`. They contain explicit paths
for this server installation, not authentication material. `stepB_prepare.sh`
creates a fresh evidence root; do not rerun it over an existing experiment.
`stepB_build_prepare.sh` creates an isolated ASPECT source copy and backs up MOOSE.
`stepB_replay.sh` compiles the compatibility harness and replays archived streams.
`stepB_run.py` runs the paired short regression; `stepB_full_batch.py` performs
three concurrent paired ASPECT rounds and five MOOSE rounds. Both preserve prior
outputs and stop at resource guards. The full batch uses original executables for
old-policy controls, including explicit old-library preload for MOOSE.

`stepB_metrics_plan.json` was frozen before the full batch. `stepB_analyze.py`,
`stepB_summary.py`, `stepB_diagnostics.py` and `stepB_source_audit.sh` reproduce
counts, paired metrics, phase checks and preservation checks. The common rho is
the upper median of pooled raw timing observations within each old/new pair;
the final summary uses ordinary medians across rounds. Fixed-period costs are
repriced at that common rho, using historical runs; no historical wall time is
used for the paired speed comparison. `stepB_moose_history_audit.py` corrects a
pre-existing residual-line counting error in the MOOSE report.

An endpoint audit found that historical C4 fixed runs continued past the reporting
cutoff, while the online input ends at 0.0063 and adds a shortened terminal step.
`stepB_analysis_correction.json` records the accounting correction: C4 costs use
the common complete-step prefix through 0.00629005, with full online counts saved
separately. Full online wall times still compare the identical 0.0063 endpoint.
The policy, input files, rho pooling rule and other cases are unchanged.

The C++ changes were tested in ASPECT and MOOSE. LaMEM and Elmer are not validated
by this experiment. The main header retains the actual server baseline's matrix
reset protection, which was missing from the older local header snapshot.
