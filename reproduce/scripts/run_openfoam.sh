#!/usr/bin/env bash
# OpenFOAM: existing seven inputs/modes, safe output ownership, true parallel path.
# NP=4 uses the supplied decomposeParDict unchanged; NP=1 is the historical baseline.
# Local PETSC_COMM_SELF PCs need separate logs/snapshots, not PBR_ALIGN broadcasts.
# Verify RC, End, time window, FATAL and .rN outputs. Parallel counts are not expected/.
# Rollback: prior script/library directory; no run/store/time directory is deleted.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init openfoam run "$@"
[[ $PROFILE == historical ]] || pbr_die 'OpenFOAM has no C1b alignment profile'
(( NP == 1 || NP == 4 )) || pbr_die "Effective NP=$NP; supplied decomposition requires NP=4 (or NP=1 for serial). Set NP explicitly."
[[ $CHECK_EXPECTED != 1 || $NP == 1 ]] || pbr_die 'expected/ contains serial baselines; parallel comparison is not applicable'
[[ $CFG =~ ^(fx|l15|l20|fine|fl30|x3|sth)$ ]] || pbr_die 'Unknown CFG'
read -r -a modes <<< "$MODES"
(( ${#modes[@]} > 0 )) || pbr_die 'MODES is empty'
for mode in "${modes[@]}"; do [[ $mode =~ ^(K1|K3|K5|ONLp|DIC)$ ]] || pbr_die "Unknown mode: $mode"; done
if [[ $CHECK_EXPECTED == 1 ]]; then
    for mode in "${modes[@]}"; do [[ $mode =~ ^(K1|K3|DIC)$ ]] || pbr_die 'CHECK_EXPECTED supports fixed K1/K3 or DIC, not timed online policies'; done
fi
if (( ROUNDS > 1 || ${#modes[@]} > 1 )); then
    overall=0
    for ((r=1; r<=ROUNDS; r++)); do
        for mode in "${modes[@]}"; do
            pbr_check_stop
            rc=0
            bash "$0" "$@" "MODES=$mode" ROUNDS=1 BACKGROUND=0 "RUN_DIR=$PBR_JOB/r${r}_${mode}" || rc=$?
            printf 'round=%s mode=%s wrapper_rc=%s\n' "$r" "$mode" "$rc" >> "$PBR_JOB/batch-status.txt"
            pbr_check_stop
            (( rc == 0 )) || overall=$rc
        done
    done
    exit "$overall"
fi
export PBR_MODE=${modes[0]}
case $CFG in
    fx) levels=10;; l15) levels=15;; fl30) levels=30;; sth) levels=5;; *) levels=20;;
esac
solver=interFoam
[[ $CFG != sth ]] || solver=interCondensatingEvaporatingFoam
pbr_need "$solver"
pbr_loaded "$(command -v "$solver")" "$FOAM_USER_LIBBIN/libpbrPETSc.so" "$FOAM_USER_LIBBIN/libpbrSolverTimer.so"
pbr_mpi "$(command -v "$solver")" "$FOAM_USER_LIBBIN/libpbrPETSc.so" "$FOAM_USER_LIBBIN/libpbrSolverTimer.so"
pbr_clear_policy
unset PBR_ALIGN PBR_ALIGNFIX PBR_POLICY PBR_K PBR_BASE PBR_UNIT PBR_COND
"$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" prepare openfoam "$PBR_ROOT" "$PBR_JOB"
cd -- "$PBR_JOB/case"
[[ ! -e 0 && -d 0.orig ]] || pbr_die 'Fresh input must contain 0.orig and no generated 0 directory'
cp -a -- 0.orig 0
if [[ $CFG == sth ]]; then
    [[ ! -e 1.36 ]] || pbr_die 'Fresh Stefan input already has generated 1.36 directory'
    cp -a -- 0 1.36
    pbr_exec initialize "$TIMEOUT" setAlphaField
else
    pbr_exec mesh "$TIMEOUT" blockMesh
    pbr_exec initialize "$TIMEOUT" setFields
fi
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=$levels PBR_PETSC_REPS=8 PBR_PETSC_BENCH=1
export PBR_PETSC_STORE=$PBR_JOB/store
export PBR_PETSC_OUT=$PBR_JOB/case/pbr_pc.csv
case $PBR_MODE in
    K*) export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=100 PBR_PETSC_FREEZE_K=${PBR_MODE#K} ;;
    ONLp) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=100 PBR_PETSC_ONLINE_POLICY=online \
        PBR_PETSC_ONLINE_RCOST=step PBR_PETSC_ONLINE_LVL=last PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1
        export PBR_PETSC_ONLINE_OUT=$PBR_JOB/case/pbr_online.csv ;;
    DIC)
        unset PBR_PETSC_OUT
        for field in p_rgh p_rghFinal; do
            pbr_exec "dic_solver_$field" "$TIMEOUT" foamDictionary system/fvSolution -entry "solvers.$field.solver" -set PCG
            pbr_exec "dic_pc_$field" "$TIMEOUT" foamDictionary system/fvSolution -entry "solvers.$field.preconditioner" -set DIC
        done ;;
esac
if (( NP > 1 )); then
    n=$(foamDictionary system/decomposeParDict -entry numberOfSubdomains -value)
    [[ $n == 4 ]] || pbr_die 'Supplied decomposition is not four subdomains; refusing to rewrite input'
    pbr_exec decompose "$TIMEOUT" decomposePar
    for ((rank=0;rank<NP;rank++)); do [[ -d processor$rank ]] || pbr_die "Missing processor$rank"; done
    pbr_finish_solve "${PBR_MPI[@]}" bash "$PBR_LIB_DIR/rank_exec.sh" "$solver" -parallel
else
    mkdir -- "$PBR_PETSC_STORE"
    pbr_finish_solve "$solver"
fi
