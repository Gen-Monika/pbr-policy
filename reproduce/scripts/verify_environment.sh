#!/usr/bin/env bash
# Report all launchers plus per-host actual linkage in isolated environments (S-01).
# No solver is started. PBR_VERIFY_SMOKE=1 enables only the two-rank MPI probe.
# Verify per-host build_report.txt; absent dependencies/unknown linkage stay explicit.
# Rollback: prior reporter/config; existing reports are retained.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_load_config environment "$@"
selected=$PBR_VERIFY_HOST
case $selected in ''|moose|lamem|aspect|elmer|openfoam) ;; *) pbr_die 'Unknown PBR_VERIFY_HOST';; esac
pbr_init "${selected:-environment}" verify "$@"
"$PBR_PYTHON" "$PBR_LIB_DIR/mpi.py" inventory | tee -a "$PBR_JOB/build_report.txt"
if [[ -z $selected ]]; then
    overall=0
    for host in moose lamem aspect elmer openfoam; do
        pbr_check_stop
        rc=0
        bash "$0" "$@" "PBR_VERIFY_HOST=$host" BACKGROUND=0 "RUN_DIR=$PBR_JOB/$host" || rc=$?
        printf 'host=%s verification_rc=%s\n' "$host" "$rc" | tee -a "$PBR_JOB/build_report.txt"
        pbr_check_stop
        (( rc == 0 )) || overall=$rc
    done
    exit "$overall"
fi
"$PBR_PYTHON" "$PBR_LIB_DIR/inspect_environment.py" "$selected" | tee -a "$PBR_JOB/build_report.txt"
if [[ $selected == openfoam ]]; then
    pbr_need interFoam
    objects=("$(command -v interFoam)" "$FOAM_USER_LIBBIN/libpbrPETSc.so" "$FOAM_USER_LIBBIN/libpbrSolverTimer.so")
else
    if [[ $selected == elmer ]]; then
        install=$(pbr_value INSTALL)
        export ELMER_HOME=$install
        export LD_LIBRARY_PATH="$install/lib/elmersolver:$install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
    pbr_resolve_binary
    objects=("$PBR_EXE")
    if [[ $selected == elmer ]]; then
        loaded=$(ldd "$PBR_EXE" | awk '/libelmersolver[.]so/ {print $3; exit}')
        [[ -n $loaded && $(readlink -f "$loaded") == "$(readlink -f "$install")/"* ]] || pbr_die 'Environment check resolves an Elmer library outside selected INSTALL'
        objects+=("$loaded")
    fi
fi
pbr_loaded "${objects[@]}"
if [[ $PBR_VERIFY_SMOKE == 1 ]]; then
    (( NP > 1 )) || pbr_die 'The MPI probe needs NP>1 CPU allowance'
    pbr_mpi "${objects[@]}"
else
    printf 'MPI runtime binding=UNVERIFIED; set PBR_VERIFY_SMOKE=1 for same-library + real two-rank collective check\n' | tee -a "$PBR_JOB/build_report.txt"
fi
