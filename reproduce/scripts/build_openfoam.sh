#!/usr/bin/env bash
# Build both required libraries into FOAM_USER_LIBBIN; no host-version equality gate.
# PETSc flags come from pkg-config or PETSC_DIR/PETSC_ARCH, including lib64.
# Verify ELF loader dependencies and rank-safe log source. Rollback: select an older
# library directory/build copy, retaining all build reports and source backups.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init openfoam build "$@"
build=$(pbr_value BUILD)
mkdir -p -- "$build"
"$PBR_PYTHON" "$PBR_LIB_DIR/sources.py" copy "$PBR_ROOT/contrib/openfoam-petsc" "$build/source" "$PBR_JOB"
pbr_petsc_flags
cd -- "$build/source"
export WM_NCOMPPROCS=$JOBS
pbr_exec plugin_build "$BUILD_TIMEOUT" wmake libso
cd -- "$build/source/pbrSolverTimer"
pbr_exec timer_build "$BUILD_TIMEOUT" wmake libso
pbr_loaded "$FOAM_USER_LIBBIN/libpbrPETSc.so" "$FOAM_USER_LIBBIN/libpbrSolverTimer.so"
pbr_need interFoam
pbr_mpi "$(command -v interFoam)" "$FOAM_USER_LIBBIN/libpbrPETSc.so" "$FOAM_USER_LIBBIN/libpbrSolverTimer.so"
printf 'build_complete=1 plugin=%s timer=%s\n' "$FOAM_USER_LIBBIN/libpbrPETSc.so" "$FOAM_USER_LIBBIN/libpbrSolverTimer.so" >> "$PBR_JOB/build_report.txt"
