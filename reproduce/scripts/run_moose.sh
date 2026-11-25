#!/usr/bin/env bash
# A-01/S-02/B-02: the official Darcy input plus documented reuse flags.
# Verify solver RC, end time and each rank trace; off keeps ALIGNFIX gated off.
# Rollback: select previous scripts/binary; each run gets a fresh retained directory.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init moose run "$@"
pbr_resolve_binary
pbr_loaded "$PBR_EXE"
pbr_mpi "$PBR_EXE"
pbr_clear_policy
"$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" prepare moose "$PBR_ROOT" "$PBR_JOB"
cd -- "$PBR_JOB/case"
export PBR_LOG=pbr.csv
pbr_finish_solve "${PBR_MPI[@]}" "$PBR_EXE" -i step6a_coupled.i \
    Outputs/exodus=false Executioner/reuse_preconditioner=true \
    Executioner/reuse_preconditioner_max_linear_its=1000000
