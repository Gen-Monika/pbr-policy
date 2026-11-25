#!/usr/bin/env bash
# A-01/S-02: build the Darcy application with its own libMesh/WASP/MPI environment.
# Verify source_changes.json, build_report.txt and mpi_smoke.log, not executable mtime.
# Rollback: restore job/source-backups and library-backups; never reset the whole tree.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
pbr_init moose build "$@"
pbr_need make
[[ -d $PBR_MOOSE_APP ]] || pbr_die 'Darcy application missing; set PBR_MOOSE_APP'
[[ -x ${LIBMESH_DIR:-}/bin/libmesh-config ]] || pbr_die 'libmesh-config missing; configure MOOSE environment/LIBMESH_DIR'
[[ -d ${WASP_DIR:-} ]] || pbr_die 'WASP_DIR missing; configure MOOSE environment'
pbr_prepare_sources
# Shared libraries may change without a new application executable. Preserve them.
"$PBR_PYTHON" - "$(pbr_value SRC)" "$PBR_JOB" <<'PY'
from pathlib import Path
import shutil,sys
src,job=map(Path,sys.argv[1:])
for path in (src/'framework').glob('libmoose-opt.so*'):
    if path.is_file():
        dest=job/'library-backups'/path.name; dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dest)
PY
pbr_exec build "$BUILD_TIMEOUT" make -C "$PBR_MOOSE_APP" -j "$JOBS" METHOD=opt
pbr_build_binary "$PBR_MOOSE_APP/darcy_thermo_mech-opt"
pbr_loaded "$PBR_EXE"
pbr_mpi "$PBR_EXE"
printf 'build_complete=1 binary=%s\n' "$PBR_EXE" >> "$PBR_JOB/build_report.txt"
