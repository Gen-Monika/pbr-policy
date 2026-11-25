#!/usr/bin/env bash
# A-03/A-07/S-02: both Fortran patches, out-of-source build, install then verify loader.
# Installation can rewrite RPATH; byte inequality alone is not an error.
# Verify libelmersolver.so resolves inside INSTALL, not an old prefix. Rollback:
# select prior INSTALL/BIN and restore source-backups; no installation is deleted.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init elmer build "$@"
pbr_need cmake
src=$(pbr_value SRC); build=$(pbr_value BUILD); install=$(pbr_value INSTALL)
pbr_prepare_sources
"$PBR_PYTHON" "$PBR_LIB_DIR/sources.py" cache "$src" "$build"
pbr_cmake_args
pbr_exec configure "$BUILD_TIMEOUT" cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release -DWITH_MPI=TRUE -DWITH_ElmerIce=TRUE "-DCMAKE_INSTALL_PREFIX=$install" "${PBR_CMAKE_ARGS[@]}"
pbr_exec build "$BUILD_TIMEOUT" cmake --build "$build" --parallel "$JOBS"
pbr_exec install "$BUILD_TIMEOUT" cmake --install "$build"
export ELMER_HOME=$install
export LD_LIBRARY_PATH="$install/lib/elmersolver:$install/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
pbr_build_binary "$install/bin/ElmerSolver"
pbr_loaded "$PBR_EXE"
loaded=$(ldd "$PBR_EXE" | awk '/libelmersolver[.]so/ {print $3; exit}')
[[ -n $loaded ]] || pbr_die 'Cannot establish loaded libelmersolver.so'
[[ $(readlink -f "$loaded") == "$(readlink -f "$install")/"* ]] || pbr_die 'ElmerSolver loads a library outside the selected INSTALL'
pbr_loaded "$loaded"
[[ -x $PBR_ELMER_GRID ]] || pbr_die 'Installed ElmerGrid missing'
pbr_mpi "$PBR_EXE" "$loaded"
printf 'build_complete=1 binary=%s solver_library=%s\n' "$PBR_EXE" "$loaded" >> "$PBR_JOB/build_report.txt"
