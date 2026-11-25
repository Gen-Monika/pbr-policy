#!/usr/bin/env bash
# ASPECT: separate build directory, matched header/integration and benchmark plugins.
# solver.cc/core.cc use verified official v2.4.0 introduction patches; already patched
# sources are accepted idempotently. Verify cache, loaded libs and plugin paths.
# Rollback: select previous BUILD/BIN; restore only listed source-backups.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init aspect build "$@"
pbr_need cmake
src=$(pbr_value SRC); build=$(pbr_value BUILD)
[[ $build != */build-pbr2 && $build != */build-pbr3 ]] || pbr_die 'Select a new ASPECT BUILD directory; preserve paper/C-step builds'
[[ -n ${PBR_ASPECT_DEAL_II_DIR:-} ]] || pbr_die 'Set PBR_ASPECT_DEAL_II_DIR'
pbr_prepare_sources
"$PBR_PYTHON" "$PBR_LIB_DIR/sources.py" cache "$src" "$build"
pbr_cmake_args
pbr_exec configure "$BUILD_TIMEOUT" cmake -S "$src" -B "$build" -DCMAKE_BUILD_TYPE=Release "-DDEAL_II_DIR=$PBR_ASPECT_DEAL_II_DIR" "${PBR_CMAKE_ARGS[@]}"
pbr_exec build "$BUILD_TIMEOUT" cmake --build "$build" --parallel "$JOBS"
pbr_build_binary "$build/aspect"
pbr_loaded "$PBR_EXE"
for benchmark in blankenbach tosi; do
    if [[ $benchmark == blankenbach ]]; then source_dir=$src/benchmarks/blankenbach/plugin
    else source_dir=$src/benchmarks/tosi_et_al_2015_gcubed; fi
    [[ -f $source_dir/CMakeLists.txt ]] || pbr_die "Official plugin source missing: $source_dir"
    plugin_build=$PBR_ASPECT_PLUGIN_DIR/$benchmark
    "$PBR_PYTHON" "$PBR_LIB_DIR/sources.py" cache "$source_dir" "$plugin_build"
    pbr_exec "plugin_${benchmark}_configure" "$BUILD_TIMEOUT" cmake -S "$source_dir" -B "$plugin_build" "-DAspect_DIR=$build" "-DDEAL_II_DIR=$PBR_ASPECT_DEAL_II_DIR"
    pbr_exec "plugin_${benchmark}_build" "$BUILD_TIMEOUT" cmake --build "$plugin_build" --parallel "$JOBS"
done
pbr_loaded "$PBR_ASPECT_PLUGIN_DIR/blankenbach/libblankenbach.so" "$PBR_ASPECT_PLUGIN_DIR/tosi/libtosi_benchmark.so"
pbr_mpi "$PBR_EXE"
printf 'build_complete=1 binary=%s plugins=%s\n' "$PBR_EXE" "$PBR_ASPECT_PLUGIN_DIR" >> "$PBR_JOB/build_report.txt"
