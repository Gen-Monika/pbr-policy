# Checksum record for the step B experiment code

`local_code_sha256.json` was written on 2026-10-17 and records the SHA-256 of the code
that produced the step B (phase-index) results. It documents that state; it is not a live
integrity check, and it is deliberately kept unchanged.

31 of the 32 entries still hash to the recorded value. The exception is `pbr_policy.h`:

| version | SHA-256 |
|---|---|
| as recorded (the code at experiment time) | `16ed56a07d1231bdea2ccad0a88f3c5eefa06a913729d7d65a933175c73da8c6` |
| as shipped in this repository | `4ecff231d4b1166d3d5b3d41c6234ac4f1081f17de0e51f928c825dfdcb15675` |

The header gained 63 lines when the portable reproduce package was added. The addition is
cross-rank alignment under `PBR_ALIGN`: rank 0's decision and timings are broadcast so that
every MPI rank carries identical policy state, in line with what the MOOSE and LaMEM
modules already did. The diff contains insertions only — no existing statement changed.

This cannot affect the step B results. Those experiments run serially: no `stepB_*` script
invokes `mpirun`, and none of them sets `PBR_ALIGN`, which did not exist at the time. The
alignment layer is a no-op in a single-rank run. In parallel runs the earlier header could
in principle let ranks reach different decisions, which is what the added layer fixes and
the reason the change was made.

The recorded hash therefore remains the correct description of the code behind the step B
numbers, and the mismatch is the record doing its job rather than an error to be
recomputed. Recomputing it would erase the information that the verified code differs from
the current one.
