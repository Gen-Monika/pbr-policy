#!/usr/bin/env bash
# A-02/S-03: explicit lamem executable target and the separate LaMEM policy header.
# Julia belongs to optional checkgetrestore, not the lamem executable target.
# A fresh no-Julia build was verified; missing Julia skips that optional check only.
# Verify integration, binary and loaded PETSc/MPI in reports. Rollback: source-backups.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init lamem build "$@"
pbr_need make
[[ -n ${PETSC_DIR:-} ]] || pbr_die 'Set PBR_LAMEM_PETSC_DIR'
src=$(pbr_value SRC)
[[ -f $src/src/Makefile && -f $src/src/LaMEM.cpp ]] || pbr_die 'Expected LaMEM repository with src/Makefile and src/LaMEM.cpp'
[[ -f $PETSC_DIR/lib/petsc/conf/variables ]] || pbr_die 'LaMEM Makefile requires PETSC_DIR/lib/petsc/conf/variables; configure an installed PETSc prefix'
pbr_prepare_sources
export PETSC_OPT=$PETSC_DIR
if command -v "$PBR_JULIA" >/dev/null 2>&1; then
    "$PBR_JULIA" --version >> "$PBR_JOB/build_report.txt"
else
    printf 'WARNING: Julia unavailable; optional checkgetrestore is skipped. Building explicit target lamem.\n' | tee -a "$PBR_JOB/build_report.txt" >&2
fi
grep -n -E 'checkgetrestore|GETRESTORE_CHECK|julia' "$src/src/Makefile" >> "$PBR_JOB/build_report.txt" || true
pbr_exec build "$BUILD_TIMEOUT" make -C "$src/src" -j "$JOBS" mode=opt lamem
pbr_build_binary "$src/bin/opt/LaMEM"
pbr_loaded "$PBR_EXE"
pbr_mpi "$PBR_EXE"
printf 'build_complete=1 binary=%s\n' "$PBR_EXE" >> "$PBR_JOB/build_report.txt"
