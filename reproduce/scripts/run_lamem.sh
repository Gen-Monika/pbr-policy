#!/usr/bin/env bash
# A-02/S-03: named input windows, current LaMEM integration and local timing gate.
# RC=83 is retained as failure, not converted to success; no equivalence/performance sweep.
# Verify inputs.json, execution-solve.json and result.json. Rollback: select prior script.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init lamem run "$@"
case $BIN in
    pbr) ;;
    orig)
        [[ -n ${PBR_LAMEM_ORIG_BIN:-} ]] || pbr_die 'Set PBR_LAMEM_ORIG_BIN for the preserved original-binary route'
        [[ $POLICY == off ]] || pbr_die 'Original binary requires POLICY=off'
        export PBR_LAMEM_BIN=$PBR_LAMEM_ORIG_BIN ;;
    *) pbr_die 'BIN must be pbr or orig' ;;
esac
[[ $COND == off ]] || pbr_die 'LaMEM has no PBR_COND extension'
pbr_resolve_binary
pbr_loaded "$PBR_EXE"
pbr_mpi "$PBR_EXE"
pbr_clear_policy
unset PBR_COND
"$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" prepare lamem "$PBR_ROOT" "$PBR_JOB"
cd -- "$PBR_JOB/case"
export PBR_LOG=pbr.csv
pbr_finish_solve "${PBR_MPI[@]}" "$PBR_EXE" -ParamFile case.dat -log_view
