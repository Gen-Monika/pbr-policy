set -e
export MAMBA_ROOT_PREFIX=/root/autodl-tmp/envs/mamba
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml OMP_NUM_THREADS=1
eval "$(/root/autodl-tmp/envs/bin/micromamba shell hook -s bash)"
micromamba activate /root/autodl-tmp/envs/moose-env
cd /root/autodl-tmp/envs/moose/src/tutorials/darcy_thermo_mech/step06_coupled_darcy_heat_conduction
make -j2 METHOD=opt
