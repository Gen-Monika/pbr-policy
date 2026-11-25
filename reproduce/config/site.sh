# Generic site defaults. No machine-specific paths. Loaded by scripts/lib/common.sh.
# Precedence: KEY=VALUE arguments > inherited environment > site.local.sh >
# explicitly selected site profile > these defaults. No solver is installed here.
# Verify effective values in each job's build_report.txt / configuration.json.
# Rollback: select the previous config; existing job directories are never reused.
: "${PBR_SITE:=none}"
: "${PBR_OUTPUT_ROOT:=${XDG_STATE_HOME:-$HOME/.local/state}/pbr}"
: "${PBR_BUILD_ROOT:=}"         # derived after all overrides have been loaded
: "${NP:=auto}"                 # min(8, affinity/cgroup CPU allowance)
: "${JOBS:=auto}"               # also capped by available memory
: "${THREADS:=1}"
: "${TIMEOUT:=7200}"
: "${BUILD_TIMEOUT:=21600}"
: "${SMOKE_TIMEOUT:=30}"
: "${KILL_AFTER:=15}"
: "${BACKGROUND:=0}"
: "${PROFILE:=historical}"      # historical | c1b; input window is recorded
: "${POLICY:=online}"
: "${K:=1}"
: "${BASE:=100}"
: "${UNIT:=solve}"
: "${COND:=off}"
: "${PBR_ALIGN:=on}"
: "${PBR_ALIGNFIX:=on}"         # only effective when PBR_ALIGN is on
: "${CASE:=blankenbach}"
: "${CFG:=fx}"
: "${MODES:=K1}"
: "${ROUNDS:=1}"
: "${BIN:=pbr}"
: "${NSTEPS:=}"                # empty selects the named profile's window
: "${LABEL:=}"
: "${RUN_DIR:=}"               # explicit fresh directory; never overwrite
: "${CHECK_EXPECTED:=0}"       # historical serial fixed OpenFOAM only
: "${PBR_VERIFY_HOST:=}"       # empty: inspect all five in isolated subprocesses
: "${PBR_VERIFY_SMOKE:=0}"     # 1: also compile/run the selected MPI infrastructure probe
: "${PBR_PYTHON:=python3}"
: "${PBR_JULIA:=julia}"
# Host keys (all optional until that host is selected):
# PBR_<HOST>_{SRC,BUILD,INSTALL,BIN,MPIEXEC,MPICC,CC,CXX,FC,PETSC_DIR,
# PETSC_ARCH,PKG_CONFIG_PATH,ENV_MODE,ENV_PREFIX,ENV_SCRIPT,ENV_MODULE,
# LD_LIBRARY_PATH,CMAKE_ARGS,MPI_ARGS,ENV_PATH,OMPI_CC,OMPI_CXX,OMPI_FC}.
# HOST is MOOSE/LAMEM/ASPECT/ELMER/OPENFOAM. ENV_PATH replaces inherited PATH;
# an explicit host LD_LIBRARY_PATH replaces inherited library paths before
# host PETSc/OpenFOAM additions. OMPI_* selects optional wrapper backends.
# ENV_MODE: existing | prefix | conda | micromamba | module | hook.
# CMAKE_ARGS and MPI_ARGS: one complete argument per line, not shell code.
# Additional keys: PBR_MOOSE_APP, PBR_MOOSE_LIBMESH_DIR, PBR_MOOSE_WASP_DIR,
# PBR_ASPECT_DEAL_II_DIR, PBR_ASPECT_PLUGIN_DIR, PBR_ELMER_GRID,
# PBR_OPENFOAM_BASHRC, PBR_OPENFOAM_LIBBIN. See script --help.
