# Explicit reference profile: PBR_SITE=autodl. Paths observed 2026-11-07.
# New builds/installs go under PBR_BUILD_ROOT, not the paper's evidence binaries.
# Verify dependencies and loaded libraries in build_report.txt. Rollback: omit profile.
PBR_OUTPUT_ROOT=/root/autodl-tmp/PBR/d0_reproduce
PBR_BUILD_ROOT=/root/autodl-tmp/PBR/d0_reproduce/builds
PBR_PYTHON=/root/miniconda3/bin/python3
PBR_MOOSE_SRC=/root/autodl-tmp/envs/moose/src
PBR_MOOSE_ENV_MODE=prefix
PBR_MOOSE_ENV_PREFIX=/root/autodl-tmp/envs/moose-env
PBR_MOOSE_PETSC_DIR=/root/autodl-tmp/envs/moose-env
PBR_MOOSE_MPIEXEC=/root/autodl-tmp/envs/moose-env/bin/mpirun
PBR_MOOSE_MPICC=/root/autodl-tmp/envs/moose-env/bin/mpicc
PBR_LAMEM_SRC=/root/autodl-tmp/envs/lamem/src
PBR_LAMEM_PETSC_DIR=/root/miniconda3
PBR_LAMEM_MPIEXEC=/root/miniconda3/bin/mpirun
PBR_LAMEM_MPICC=/root/miniconda3/bin/mpicc
PBR_LAMEM_ENV_PATH=/root/miniconda3/bin:/usr/bin:/bin:/usr/sbin:/sbin
PBR_LAMEM_OMPI_CC=/usr/bin/gcc
PBR_LAMEM_OMPI_CXX=/usr/bin/g++
PBR_ASPECT_SRC=/root/autodl-tmp/PBR/stepB/phase_index_20261017_codex/aspect_source
PBR_ASPECT_DEAL_II_DIR=/root/autodl-tmp/envs/dealii-deb/usr/share/cmake/deal.II
PBR_ASPECT_LD_LIBRARY_PATH=/root/autodl-tmp/envs/dealii-deb/usr/lib/x86_64-linux-gnu
PBR_ASPECT_MPIEXEC=/usr/bin/mpirun
PBR_ASPECT_MPICC=/usr/bin/mpicc
PBR_ASPECT_ENV_PATH=/usr/bin:/bin:/usr/sbin:/sbin
PBR_ELMER_SRC=/root/autodl-tmp/envs/elmer-src
PBR_ELMER_ENV_MODE=hook
PBR_ELMER_ENV_SCRIPT=/root/autodl-tmp/envs/elmerenv.sh
PBR_ELMER_MPIEXEC=/usr/bin/mpirun
PBR_ELMER_MPICC=/usr/bin/mpicc
PBR_ELMER_ENV_PATH=/usr/bin:/bin:/usr/sbin:/sbin
PBR_ELMER_LD_LIBRARY_PATH=/root/autodl-tmp/envs/elmer-install/lib/elmersolver:/root/autodl-tmp/envs/elmer-install/lib
# Installed runtime BLAS/LAPACK have no unversioned development symlinks here.
# These are build/dependency options, independent of the case's solver settings.
PBR_ELMER_CMAKE_ARGS='-DBLAS_LIBRARIES=/usr/lib/x86_64-linux-gnu/libblas.so.3
-DLAPACK_LIBRARIES=/usr/lib/x86_64-linux-gnu/liblapack.so.3
-DWITH_ELMERGUI=FALSE
-DWITH_ELMERPOST=FALSE
-DWITH_LUA=TRUE'
PBR_OPENFOAM_BASHRC=/usr/lib/openfoam/openfoam2406/etc/bashrc
PBR_OPENFOAM_PETSC_DIR=/root/miniconda3
PBR_OPENFOAM_MPIEXEC=/root/miniconda3/bin/mpirun
PBR_OPENFOAM_MPICC=/root/miniconda3/bin/mpicc
PBR_OPENFOAM_OMPI_CC=/usr/bin/gcc
PBR_OPENFOAM_ENV_PATH=/root/miniconda3/bin:/usr/bin:/bin:/usr/sbin:/sbin
