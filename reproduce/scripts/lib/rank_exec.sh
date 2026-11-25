#!/usr/bin/env bash
# Keep OpenFOAM binary snapshots separate without changing PC/policy semantics.
# Verify store.rN directories; rollback: select NP=1 (bare store path).
set -euo pipefail
rank=${OMPI_COMM_WORLD_RANK:-${PMI_RANK:-${PMIX_RANK:-}}}
[[ $rank =~ ^[0-9]+$ ]] || { echo 'MPI rank is unknown; refusing shared snapshots' >&2; exit 2; }
export PBR_PETSC_STORE="${PBR_PETSC_STORE:?}.r$rank"
mkdir -p -- "$PBR_PETSC_STORE"
exec "$@"
