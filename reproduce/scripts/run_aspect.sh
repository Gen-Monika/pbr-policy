#!/usr/bin/env bash
# ASPECT: matched plugins, C1 rank traces, explicit historical/C-step time windows.
# No plugin source is downloaded; build_aspect.sh uses the selected official tree.
# Verify loaded libraries, effective input and trace.csv[.rN]. Rollback: prior BIN/config.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init aspect run "$@"
case $CASE in
    blankenbach) prm=case.prm; plugin=$PBR_ASPECT_PLUGIN_DIR/blankenbach/libblankenbach.so ;;
    tosi1|tosi3|tosi4|tosi5) prm=Tosi_Case${CASE#tosi}.prm; plugin=$PBR_ASPECT_PLUGIN_DIR/tosi/libtosi_benchmark.so
        [[ $PROFILE != c1b ]] || pbr_die 'C1b ASPECT profile is Blankenbach only' ;;
    *) pbr_die 'CASE must be blankenbach/tosi1/tosi3/tosi4/tosi5' ;;
esac
pbr_resolve_binary
pbr_loaded "$PBR_EXE" "$plugin"
pbr_mpi "$PBR_EXE" "$plugin"
pbr_clear_policy
"$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" prepare aspect "$PBR_ROOT" "$PBR_JOB"
cd -- "$PBR_JOB/case"
if [[ $CASE == blankenbach ]]; then
    cp -- "$plugin" plugin/libblankenbach.so
else
    cp -- "$plugin" libtosi_benchmark.so
fi
export PBR_LOG=trace.csv
pbr_finish_solve "${PBR_MPI[@]}" "$PBR_EXE" "$prm"
