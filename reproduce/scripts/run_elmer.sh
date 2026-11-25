#!/usr/bin/env bash
# A-03..07: use stabilized.sif, correct Solver 2 switch, complete input directory,
# and documented geometric partition N x 1. ElmerGrid requires the third axis
# explicitly: N 1 1 reproduces all 40 archived C-step partition files bytewise.
# Verify RC, ALL DONE, per-rank traces and reference check SEPARATELY. np8's known
# reference FAILED is disclosed, not hidden or investigated. Partition and process
# count effects were not separated; this route covers only this FSSA input.
# Rollback: prior INSTALL/config; preserve run directories and partition logs.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init elmer run "$@"
[[ $COND == off ]] || pbr_die 'Elmer does not implement PBR_COND'
[[ $UNIT == solve ]] || pbr_die 'Elmer implements solve-level decisions only'
[[ $POLICY != fixed || $K == 1 ]] || pbr_die 'Elmer fixed interface currently supports native K=1 only'
install=$(pbr_value INSTALL)
export ELMER_HOME=$install
export LD_LIBRARY_PATH="$install/lib/elmersolver:$install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
pbr_resolve_binary
pbr_loaded "$PBR_EXE"
loaded=$(ldd "$PBR_EXE" | awk '/libelmersolver[.]so/ {print $3; exit}')
[[ -n $loaded ]] || pbr_die 'Cannot establish Elmer solver library'
[[ $(readlink -f "$loaded") == "$(readlink -f "$install")/"* ]] || pbr_die 'Selected ElmerSolver loads an old/different INSTALL library'
pbr_loaded "$loaded"
pbr_mpi "$PBR_EXE" "$loaded"
pbr_clear_policy
unset PBR_POLICY PBR_K PBR_UNIT PBR_COND
"$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" prepare elmer "$PBR_ROOT" "$PBR_JOB"
cd -- "$PBR_JOB/case"
if (( NP > 1 )); then
    [[ -x $PBR_ELMER_GRID ]] || pbr_die 'ElmerGrid missing: set PBR_ELMER_GRID'
    pbr_exec partition "$TIMEOUT" "$PBR_ELMER_GRID" 2 2 mesh2D -partition "$NP" 1 1
    [[ -d mesh2D/partitioning.$NP ]] || pbr_die 'ElmerGrid did not produce the requested geometric partition'
fi
export PBR_LOG=pbr_trace.csv
# POLICY remains the wrapper setting; PBR_POLICY is intentionally absent for Fortran.
pbr_finish_solve "${PBR_MPI[@]}" "$PBR_EXE" stabilized.sif
