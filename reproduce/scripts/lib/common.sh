#!/usr/bin/env bash
# Shared launch/build plumbing: S-01, A-01..07, B-04..06 and D0 portability 1..19.
# Policies remain in separate host implementations. Verify configuration.json,
# build_report.txt, execution-*.json and result.json, not timestamps alone.
# Rollback: use prior scripts/config; keep jobs and restore explicit source backups.

PBR_LIB_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PBR_PACKAGE_DEFAULT=$(cd -- "$PBR_LIB_DIR/../.." && pwd)

pbr_die() { printf 'PBR ERROR: %s\n' "$*" >&2; exit 2; }
pbr_warn() { printf 'PBR WARNING: %s\n' "$*" >&2; }
pbr_need() { command -v "$1" >/dev/null 2>&1 || pbr_die "Missing command: $1"; }
pbr_value() { local key="PBR_${PBR_HOST^^}_$1"; printf '%s' "${!key:-}"; }
pbr_default_host() { local key="PBR_${PBR_HOST^^}_$1"; [[ -n ${!key:-} ]] || printf -v "$key" '%s' "$2"; export "$key"; }

pbr_keys() {
    PBR_CONFIG_KEYS=(PBR_ROOT PBR_SITE PBR_OUTPUT_ROOT PBR_BUILD_ROOT PBR_PYTHON PBR_JULIA
        NP JOBS THREADS TIMEOUT BUILD_TIMEOUT SMOKE_TIMEOUT KILL_AFTER BACKGROUND PROFILE
        POLICY K BASE UNIT COND PBR_ALIGN PBR_ALIGNFIX CASE CFG MODES ROUNDS BIN NSTEPS LABEL
        RUN_DIR CHECK_EXPECTED PBR_VERIFY_HOST PBR_VERIFY_SMOKE PBR_MOOSE_APP PBR_MOOSE_LIBMESH_DIR PBR_MOOSE_WASP_DIR
        PBR_ASPECT_DEAL_II_DIR PBR_ASPECT_PLUGIN_DIR PBR_ELMER_GRID PBR_OPENFOAM_BASHRC
        PBR_OPENFOAM_LIBBIN PBR_LAMEM_ORIG_BIN)
    local host field
    for host in MOOSE LAMEM ASPECT ELMER OPENFOAM; do
        for field in SRC BUILD INSTALL BIN MPIEXEC MPICC CC CXX FC OMPI_CC OMPI_CXX OMPI_FC PETSC_DIR PETSC_ARCH PKG_CONFIG_PATH ENV_MODE ENV_PREFIX ENV_SCRIPT ENV_MODULE ENV_PATH LD_LIBRARY_PATH CMAKE_ARGS MPI_ARGS; do
            PBR_CONFIG_KEYS+=("PBR_${host}_$field")
        done
    done
}

pbr_load_config() {
    PBR_HOST=$1; shift
    pbr_keys
    local key arg selector local_config
    local -A inherited=() cli=() allowed=()
    for key in "${PBR_CONFIG_KEYS[@]}"; do
        allowed[$key]=1
        [[ ! -v $key ]] || inherited[$key]=${!key}
    done
    for arg in "$@"; do
        if [[ $arg == --help || $arg == -h ]]; then
            printf '%s\n' 'Usage: bash scripts/{build,run}_HOST.sh [KEY=VALUE ...]' \
              'Precedence: command arguments > environment > config/site.local.sh > selected site > defaults.' \
              'PBR_SITE=autodl explicitly selects the reference machine. Linux+Bash+Python3 required.' \
              'NP defaults to min(8, available CPUs); OpenFOAM parallel inputs require explicit NP=4.' \
              'PROFILE=historical|c1b POLICY=off|fixed|online; host restrictions are checked.' \
              'Output: PBR_OUTPUT_ROOT; builds: PBR_BUILD_ROOT; RUN_DIR must not exist.' \
              'BACKGROUND=1 detaches; manage with: python3 scripts/lib/pbr.py job status|wait|stop JOB_DIR' \
              'Build/run environment: PBR_HOST_{SRC,BUILD,INSTALL,BIN,MPIEXEC,MPICC,PETSC_DIR,PETSC_ARCH,...}.' \
              'MPI_ARGS/CMAKE_ARGS contain one argument per line. No shell eval is used.' \
              'Timeouts are seconds: TIMEOUT, BUILD_TIMEOUT, SMOKE_TIMEOUT, KILL_AFTER.'
            exit 0
        fi
        [[ $arg == *=* ]] || pbr_die "Use KEY=VALUE, not positional argument: $arg"
        key=${arg%%=*}
        [[ ${allowed[$key]:-} == 1 ]] || pbr_die "Unknown setting: $key"
        cli[$key]=${arg#*=}
    done
    PBR_ROOT=${cli[PBR_ROOT]:-${inherited[PBR_ROOT]:-$PBR_PACKAGE_DEFAULT}}
    [[ -d $PBR_ROOT/cases && -f $PBR_ROOT/config/site.sh ]] || pbr_die 'PBR_ROOT must name reproduce/, not the repository root'
    PBR_ROOT=$(cd -- "$PBR_ROOT" && pwd)
    # Defaults must not derive from a partially inherited configuration.
    for key in "${PBR_CONFIG_KEYS[@]}"; do [[ $key == PBR_ROOT ]] || unset "$key"; done
    source "$PBR_ROOT/config/site.sh"
    selector=${cli[PBR_SITE]:-${inherited[PBR_SITE]:-none}}
    case $selector in
        none|'') ;;
        autodl) source "$PBR_ROOT/config/site.autodl.sh" ;;
        *) pbr_die 'PBR_SITE must be none or autodl; custom overrides belong in config/site.local.sh' ;;
    esac
    local_config=$PBR_ROOT/config/site.local.sh
    [[ ! -f $local_config ]] || source "$local_config"
    for key in "${!inherited[@]}"; do printf -v "$key" '%s' "${inherited[$key]}"; done
    for key in "${!cli[@]}"; do printf -v "$key" '%s' "${cli[$key]}"; done
    PBR_SITE=$selector
    : "${PBR_BUILD_ROOT:=$PBR_OUTPUT_ROOT/builds}"
    for key in "${PBR_CONFIG_KEYS[@]}"; do [[ ! -v $key ]] || export "$key"; done
}

pbr_exec() {
    local name=$1 seconds=$2; shift 2
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" execute "$PBR_JOB" "$name" "$seconds" "$KILL_AFTER" -- "$@"
}

pbr_check_stop() {
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" check-stop "$PBR_JOB"
}

pbr_source_environment() {
    local file=$1 rc=0
    [[ -f $file ]] || pbr_die "Environment file does not exist: $file"
    # Some vendor bashrc files use unset variables and return 1 on success.
    set +eu
    # Vendor bashrc files iterate over "$@" (e.g. OpenFOAM treats each arg as a
    # settings file and re-sources itself). Inside a function "$@" is this
    # function's arguments, so it must be cleared before sourcing or the file
    # recurses into itself until the stack overflows (SIGSEGV).
    set --
    source "$file" || rc=$?
    set -Eeuo pipefail
    [[ $rc == 0 ]] || pbr_warn "Environment script returned $rc; checking actual commands/libraries: $file"
}

activate_env() {
    local mode prefix script hook module_name key val
    mode=$(pbr_value ENV_MODE); mode=${mode:-existing}
    prefix=$(pbr_value ENV_PREFIX); script=$(pbr_value ENV_SCRIPT)
    val=$(pbr_value ENV_PATH); [[ -z $val ]] || export PATH=$val
    unset OMPI_CC OMPI_CXX OMPI_FC
    for key in OMPI_CC OMPI_CXX OMPI_FC; do val=$(pbr_value "$key"); [[ -z $val ]] || export "$key=$val"; done
    case $mode in
        existing) ;;
        prefix) [[ -d $prefix/bin ]] || pbr_die 'ENV_PREFIX/bin missing'; export PATH="$prefix/bin:$PATH" ;;
        hook) pbr_source_environment "$script" ;;
        module)
            [[ -z $script ]] || pbr_source_environment "$script"
            command -v module >/dev/null || pbr_die 'module command unavailable; set ENV_SCRIPT'
            module_name=$(pbr_value ENV_MODULE); [[ -n $module_name ]] || pbr_die 'ENV_MODULE is empty'
            module load "$module_name" ;;
        conda|micromamba)
            pbr_need "$mode"
            [[ -n $prefix ]] || pbr_die 'ENV_PREFIX is empty'
            hook=$PBR_JOB/activation.sh
            if [[ $mode == conda ]]; then conda shell.bash hook > "$hook"
            else micromamba shell hook --shell bash > "$hook"; fi
            pbr_source_environment "$hook"
            "$mode" activate "$prefix" ;;
        *) pbr_die "Unknown ENV_MODE=$mode" ;;
    esac
    if [[ $PBR_HOST == moose && -n $prefix ]]; then
        export LIBMESH_DIR=${PBR_MOOSE_LIBMESH_DIR:-$prefix}
        export WASP_DIR=${PBR_MOOSE_WASP_DIR:-$prefix}
    fi
    [[ -z $(pbr_value SRC) || $PBR_HOST != moose ]] || export MOOSE_DIR="$(pbr_value SRC)"
    for key in CC CXX FC; do val=$(pbr_value "$key"); [[ -z $val ]] || export "$key=$val"; done
    val=$(pbr_value LD_LIBRARY_PATH)
    # An explicit host loader path replaces inherited paths. Appending a conda
    # path here can silently replace a system MPI/PMIx with same-SONAME libraries.
    [[ -z $val ]] || export LD_LIBRARY_PATH="$val"
    unset PETSC_DIR PETSC_ARCH
    val=$(pbr_value PETSC_DIR); [[ -z $val ]] || export PETSC_DIR=$val
    val=$(pbr_value PETSC_ARCH); [[ -z $val ]] || export PETSC_ARCH=$val
    val=$(pbr_value PKG_CONFIG_PATH)
    [[ -z $val ]] || export PKG_CONFIG_PATH="$val${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    if [[ -n ${PETSC_DIR:-} ]]; then
        local base
        for base in "$PETSC_DIR/${PETSC_ARCH:-}" "$PETSC_DIR"; do
            for val in "$base/lib" "$base/lib64"; do
                [[ ! -d $val ]] || export LD_LIBRARY_PATH="$val${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
                [[ ! -d $val/pkgconfig ]] || export PKG_CONFIG_PATH="$val/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
            done
        done
    fi
    export OMP_NUM_THREADS=$THREADS OPENBLAS_NUM_THREADS=$THREADS MKL_NUM_THREADS=$THREADS
    export BLIS_NUM_THREADS=$THREADS VECLIB_MAXIMUM_THREADS=$THREADS
    export HWLOC_COMPONENTS=${HWLOC_COMPONENTS:--opencl,-gl,-cuda,-nvml}
    if [[ $PBR_HOST == openfoam ]]; then
        if [[ -n ${PBR_OPENFOAM_BASHRC:-} ]]; then pbr_source_environment "$PBR_OPENFOAM_BASHRC"; fi
        [[ -n ${WM_PROJECT_DIR:-} && -d ${WM_PROJECT_DIR:-} ]] || pbr_die 'Load OpenFOAM or set PBR_OPENFOAM_BASHRC'
        pbr_need wmake
        export FOAM_USER_LIBBIN=${PBR_OPENFOAM_LIBBIN:-$PBR_BUILD_ROOT/openfoam/lib}
        mkdir -p -- "$FOAM_USER_LIBBIN"
        export LD_LIBRARY_PATH="$FOAM_USER_LIBBIN${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
}

pbr_init() {
    PBR_KIND=$2; local host=$1; shift 2
    pbr_load_config "$host" "$@"
    set -Eeuo pipefail
    [[ $(uname -s) == Linux ]] || pbr_die 'Runtime/build entry points support Linux only; bash -n works on other systems'
    pbr_need "$PBR_PYTHON"
    local resources values
    resources=$("$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" resources)
    values=$("$PBR_PYTHON" -c 'import json,sys; r=json.loads(sys.argv[1]); print(r["default_np"],r["default_jobs"],r["available_cpus"])' "$resources")
    read -r PBR_DEFAULT_NP PBR_DEFAULT_JOBS PBR_AVAILABLE_CPUS <<< "$values"
    [[ $NP != auto ]] || NP=$PBR_DEFAULT_NP
    [[ $JOBS != auto ]] || JOBS=$PBR_DEFAULT_JOBS
    local key
    for key in NP JOBS THREADS ROUNDS; do [[ ${!key} =~ ^[1-9][0-9]*$ ]] || pbr_die "$key must be a positive integer"; done
    for key in TIMEOUT BUILD_TIMEOUT SMOKE_TIMEOUT KILL_AFTER BASE K; do [[ ${!key} =~ ^[0-9]+$ ]] || pbr_die "$key must be a nonnegative integer"; done
    (( NP * THREADS <= PBR_AVAILABLE_CPUS )) || pbr_die "NP*THREADS exceeds effective CPU allowance $PBR_AVAILABLE_CPUS"
    (( JOBS <= PBR_AVAILABLE_CPUS )) || pbr_die "JOBS exceeds effective CPU allowance $PBR_AVAILABLE_CPUS"
    [[ $PROFILE == historical || $PROFILE == c1b ]] || pbr_die 'Unknown PROFILE'
    [[ $POLICY == off || $POLICY == fixed || $POLICY == online ]] || pbr_die 'Unknown POLICY'
    [[ $PBR_ALIGN == on || $PBR_ALIGN == off ]] || pbr_die 'PBR_ALIGN must be on or off'
    [[ $COND == off || $COND == index ]] || pbr_die 'COND must be off or index'
    [[ $UNIT == solve || $UNIT == step ]] || pbr_die 'UNIT must be solve or step'
    [[ $BACKGROUND == 0 || $BACKGROUND == 1 ]] || pbr_die 'BACKGROUND must be 0 or 1'
    [[ $PBR_ALIGNFIX == on || $PBR_ALIGNFIX == off ]] || pbr_die 'PBR_ALIGNFIX must be on or off'
    [[ $CHECK_EXPECTED == 0 || $CHECK_EXPECTED == 1 ]] || pbr_die 'CHECK_EXPECTED must be 0 or 1'
    [[ $PBR_VERIFY_SMOKE == 0 || $PBR_VERIFY_SMOKE == 1 ]] || pbr_die 'PBR_VERIFY_SMOKE must be 0 or 1'
    [[ $LABEL =~ ^[A-Za-z0-9_.-]*$ ]] || pbr_die 'LABEL may contain only letters, digits, dot, underscore and hyphen'
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" check-paths "$PBR_ROOT" "$PBR_OUTPUT_ROOT" "$PBR_BUILD_ROOT" "$RUN_DIR"
    mkdir -p -- "$PBR_OUTPUT_ROOT/$host" "$PBR_BUILD_ROOT"
    if [[ -n $RUN_DIR ]]; then
        [[ ! -e $RUN_DIR ]] || pbr_die "RUN_DIR already exists: $RUN_DIR"
        mkdir -- "$RUN_DIR"
        PBR_JOB=$(cd -- "$RUN_DIR" && pwd)
    else
        PBR_JOB=$(mktemp -d "$PBR_OUTPUT_ROOT/$host/${PBR_KIND}-${PROFILE}-np${NP}-${PBR_ALIGN}-${LABEL:-job}.XXXXXXXX")
    fi
    export PBR_JOB NP JOBS THREADS
    printf '{"finished":false}\n' > "$PBR_JOB/status.json"
    printf '%s\n' "$resources" > "$PBR_JOB/resources.json"
    trap 'rc=$?; trap - EXIT; "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" status "$PBR_JOB" "$rc"; exit "$rc"' EXIT
    pbr_check_stop
    printf 'PBR job=%s host=%s NP=%s JOBS=%s PROFILE=%s\n' "$PBR_JOB" "$host" "$NP" "$JOBS" "$PROFILE"
    if [[ $BACKGROUND == 1 ]]; then
        "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" background "$PBR_JOB" -- bash "$0" "$@" BACKGROUND=0 "RUN_DIR=$PBR_JOB/worker"
        exit 0
    fi
    pbr_default_host BUILD "$PBR_BUILD_ROOT/$host"
    pbr_default_host INSTALL "$(pbr_value BUILD)/install"
    case $host in
        moose)
            : "${PBR_MOOSE_APP:=$(pbr_value SRC)/tutorials/darcy_thermo_mech/step06_coupled_darcy_heat_conduction}"
            pbr_default_host BIN "$PBR_MOOSE_APP/darcy_thermo_mech-opt" ;;
        lamem) pbr_default_host BIN "$(pbr_value SRC)/bin/opt/LaMEM" ;;
        aspect)
            pbr_default_host BIN "$(pbr_value BUILD)/aspect"
            : "${PBR_ASPECT_PLUGIN_DIR:=$(pbr_value BUILD)/pbr-plugins}" ;;
        elmer)
            pbr_default_host BIN "$(pbr_value INSTALL)/bin/ElmerSolver"
            : "${PBR_ELMER_GRID:=$(pbr_value INSTALL)/bin/ElmerGrid}" ;;
    esac
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" check-paths "$PBR_ROOT" "$(pbr_value BUILD)" "$(pbr_value INSTALL)" "${PBR_ASPECT_PLUGIN_DIR:-}" "${PBR_OPENFOAM_LIBBIN:-}"
    for key in "${PBR_CONFIG_KEYS[@]}"; do [[ ! -v $key ]] || export "$key"; done
    activate_env
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" configuration "$PBR_JOB/configuration.json" "${PBR_CONFIG_KEYS[@]}"
    {
        printf 'host=%s kind=%s NP=%s JOBS=%s THREADS=%s PROFILE=%s\n' "$host" "$PBR_KIND" "$NP" "$JOBS" "$THREADS" "$PROFILE"
        printf 'site=%s package=%s\n' "$PBR_SITE" "$PBR_ROOT"
        cat "$PBR_JOB/resources.json"
        df -Pk "$PBR_JOB" "$PBR_BUILD_ROOT"
        for key in CC CXX FC; do
            local command=${!key:-}; [[ -n $command ]] || continue
            printf '%s=%s\n' "$key" "$command"
            "$command" --version 2>&1 | head -n 2 || true
        done
        for key in PETSC_DIR PETSC_ARCH LIBMESH_DIR WASP_DIR WM_PROJECT_VERSION WM_PROJECT_DIR WM_OPTIONS WM_PRECISION_OPTION WM_LABEL_SIZE FOAM_USER_LIBBIN; do printf '%s=%s\n' "$key" "${!key:-}"; done
    } > "$PBR_JOB/build_report.txt"
    "$PBR_PYTHON" "$PBR_LIB_DIR/inspect_environment.py" "$PBR_HOST" >> "$PBR_JOB/build_report.txt"
}

pbr_clear_policy() {
    local name
    while read -r name; do unset "$name"; done < <(compgen -v | grep '^PBR_PETSC_' || true)
    unset PBR_POLICY PBR_K PBR_BASE PBR_UNIT PBR_COND PBR_LOG
    export PBR_POLICY=$POLICY PBR_K=$K PBR_BASE=$BASE PBR_UNIT=$UNIT PBR_COND=$COND
    export PBR_ALIGN PBR_ALIGNFIX
}

pbr_resolve_binary() {
    PBR_EXE=$(pbr_value BIN)
    [[ -n $PBR_EXE ]] || pbr_die 'Host BIN is not configured'
    PBR_EXE=$(command -v "$PBR_EXE") || pbr_die "Executable not found: $(pbr_value BIN)"
    [[ -x $PBR_EXE ]] || pbr_die "Not executable: $PBR_EXE"
    PBR_EXE=$(readlink -f "$PBR_EXE")
}

pbr_build_binary() {
    pbr_resolve_binary
    [[ $PBR_EXE == "$(readlink -f "$1")" ]] || pbr_die "BIN does not identify this build's artifact: $1"
}

pbr_loaded() {
    local file out
    for file in "$@"; do
        [[ -f $file ]] || pbr_die "Missing binary/library: $file"
        out=$(ldd "$file" 2>&1 || true)
        { printf '\nloaded_object=%s\n' "$(readlink -f "$file")"; sha256sum "$file"; printf '%s\n' "$out"; } >> "$PBR_JOB/build_report.txt"
        [[ $out != *'not found'* ]] || pbr_die "Unresolved library for $file (see build_report.txt)"
    done
}

pbr_mpi() {
    PBR_MPI=()
    (( NP > 1 )) || return 0
    local launcher compiler val launcher_version
    launcher=$(pbr_value MPIEXEC)
    if [[ -z $launcher ]]; then
        mapfile -t candidates < <("$PBR_PYTHON" "$PBR_LIB_DIR/mpi.py" launchers)
        (( ${#candidates[@]} == 1 )) || pbr_die 'MPI launcher unknown/ambiguous; set per-host MPIEXEC (see verify_environment.sh)'
        launcher=${candidates[0]}
    fi
    launcher=$(command -v "$launcher") || pbr_die 'Configured MPI launcher unavailable'
    PBR_MPI=("$launcher")
    val=$("$launcher" --version 2>&1 || true)
    launcher_version=$val
    printf '\nlauncher=%s\n%s\n' "$launcher" "$val" >> "$PBR_JOB/build_report.txt"
    if [[ $(id -u) == 0 && $val =~ (Open[[:space:]]MPI|OpenRTE|Open[[:space:]]RTE) ]]; then PBR_MPI+=(--allow-run-as-root); fi
    while IFS= read -r val; do [[ -z $val ]] || PBR_MPI+=("$val"); done <<< "$(pbr_value MPI_ARGS)"
    compiler=$(pbr_value MPICC)
    [[ -n $compiler ]] || compiler="$(dirname "$launcher")/mpicc"
    compiler=$(command -v "$compiler") || pbr_die 'MPI wrapper unknown; set per-host MPICC'
    pbr_exec mpi_compile "$SMOKE_TIMEOUT" "$compiler" "$PBR_LIB_DIR/mpi_smoke.c" -o "$PBR_JOB/mpi_smoke"
    "$PBR_PYTHON" "$PBR_LIB_DIR/mpi.py" match "$PBR_JOB/mpi_smoke" "$@" >> "$PBR_JOB/build_report.txt"
    printf '%s\n' "$launcher_version" > "$PBR_JOB/launcher-version.txt"
    "$PBR_PYTHON" "$PBR_LIB_DIR/mpi.py" library-version "$PBR_JOB/mpi_smoke" > "$PBR_JOB/mpi-library-version.txt"
    "$PBR_PYTHON" "$PBR_LIB_DIR/mpi.py" version "$PBR_JOB/launcher-version.txt" "$PBR_JOB/mpi-library-version.txt" >> "$PBR_JOB/build_report.txt"
    pbr_exec mpi_smoke "$SMOKE_TIMEOUT" "${PBR_MPI[@]}" -np 2 "$PBR_JOB/mpi_smoke"
    grep -q '^PBR_MPI_OK size=2 sum=1$' "$PBR_JOB/mpi_smoke.log" || pbr_die 'MPI smoke did not confirm two communicating ranks'
    [[ $(grep -c '^PBR_MPI_RANK ' "$PBR_JOB/mpi_smoke.log") == 2 ]] || pbr_die 'MPI smoke rank count is not two'
    "$PBR_PYTHON" "$PBR_LIB_DIR/mpi.py" version "$PBR_JOB/launcher-version.txt" "$PBR_JOB/mpi_smoke.log" >> "$PBR_JOB/build_report.txt"
    PBR_MPI+=(-np "$NP")
}

pbr_finish_solve() {
    local rc=0 summary_rc=0
    pbr_check_stop
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" effective-inputs "$PBR_JOB"
    local -a runtime_keys=(NP JOBS THREADS PROFILE POLICY K BASE UNIT COND PBR_ALIGN PBR_ALIGNFIX
        PBR_POLICY PBR_K PBR_BASE PBR_UNIT PBR_COND PBR_LOG PBR_MODE
        PETSC_DIR PETSC_ARCH OMP_NUM_THREADS OPENBLAS_NUM_THREADS MKL_NUM_THREADS BLIS_NUM_THREADS
        VECLIB_MAXIMUM_THREADS FOAM_USER_LIBBIN ELMER_HOME LD_LIBRARY_PATH)
    local name
    while read -r name; do runtime_keys+=("$name"); done < <(compgen -v | grep '^PBR_PETSC_' || true)
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" configuration "$PBR_JOB/runtime.json" "${runtime_keys[@]}"
    pbr_exec solve "$TIMEOUT" "$@" || rc=$?
    "$PBR_PYTHON" "$PBR_LIB_DIR/pbr.py" summarize "$PBR_HOST" "$PBR_ROOT" "$PBR_JOB" > "$PBR_JOB/result-summary.txt" || summary_rc=$?
    printf 'solver_rc=%s validation_rc=%s job=%s\n' "$rc" "$summary_rc" "$PBR_JOB"
    (( rc == 0 )) || return "$rc"
    return "$summary_rc"
}

pbr_cmake_args() {
    PBR_CMAKE_ARGS=(); local item key
    for key in CC CXX FC; do
        item=$(pbr_value "$key"); [[ -n $item ]] || continue
        case $key in CC) PBR_CMAKE_ARGS+=("-DCMAKE_C_COMPILER=$item");; CXX) PBR_CMAKE_ARGS+=("-DCMAKE_CXX_COMPILER=$item");; FC) PBR_CMAKE_ARGS+=("-DCMAKE_Fortran_COMPILER=$item");; esac
    done
    while IFS= read -r item; do [[ -z $item ]] || PBR_CMAKE_ARGS+=("$item"); done <<< "$(pbr_value CMAKE_ARGS)"
}

pbr_prepare_sources() {
    [[ -d $(pbr_value SRC) ]] || pbr_die 'Configure the host SRC directory first'
    "$PBR_PYTHON" "$PBR_LIB_DIR/sources.py" "$PBR_HOST" "$PBR_ROOT" "$(pbr_value SRC)" "$PBR_JOB"
}

pbr_petsc_flags() {
    local package=PETSc base lib inc
    if command -v pkg-config >/dev/null && pkg-config --exists "$package"; then
        if [[ -n ${PETSC_DIR:-} ]]; then
            base=$(pkg-config --variable=prefix "$package")
            [[ $(readlink -f "$base") == "$(readlink -f "$PETSC_DIR")" || $(readlink -f "$base") == "$(readlink -f "$PETSC_DIR/${PETSC_ARCH:-}")" ]] || pbr_die 'pkg-config resolves another PETSc; configure the per-host PKG_CONFIG_PATH'
        fi
        export PBR_PETSC_CPPFLAGS="$(pkg-config --cflags "$package")"
        export PBR_PETSC_LDFLAGS="$(pkg-config --libs "$package")"
        pkg-config --modversion "$package" >> "$PBR_JOB/build_report.txt"
    else
        [[ -n ${PETSC_DIR:-} && -f $PETSC_DIR/include/petsc.h ]] || pbr_die 'Set host PETSC_DIR/PETSC_ARCH or provide PETSc pkg-config metadata'
        inc="-I$PETSC_DIR/include"
        [[ -z ${PETSC_ARCH:-} ]] || inc+=" -I$PETSC_DIR/$PETSC_ARCH/include"
        lib=''
        for base in "$PETSC_DIR/${PETSC_ARCH:-}" "$PETSC_DIR"; do
            for candidate in "$base/lib" "$base/lib64"; do
                if compgen -G "$candidate/libpetsc.so*" >/dev/null; then lib=$candidate; break 2; fi
            done
        done
        [[ -n $lib ]] || pbr_die 'PETSc shared library missing; static installations require complete pkg-config link metadata'
        export PBR_PETSC_CPPFLAGS=$inc PBR_PETSC_LDFLAGS="-L$lib -lpetsc"
    fi
    printf 'PETSc_CPPFLAGS=%s\nPETSc_LDFLAGS=%s\n' "$PBR_PETSC_CPPFLAGS" "$PBR_PETSC_LDFLAGS" >> "$PBR_JOB/build_report.txt"
}
