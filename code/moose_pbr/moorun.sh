#!/bin/bash
# moorun.sh <label> <input.i (relative to step06 dir)> [extra CLI args...]
export MAMBA_ROOT_PREFIX=/root/autodl-tmp/envs/mamba
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml OMP_NUM_THREADS=1
eval "$(/root/autodl-tmp/envs/bin/micromamba shell hook -s bash)"
micromamba activate /root/autodl-tmp/envs/moose-env
S=/root/autodl-tmp/envs/moose/src/tutorials/darcy_thermo_mech/step06_coupled_darcy_heat_conduction
L=$1; IN=$2; shift 2
W=/root/autodl-tmp/PBR/moose_cases/$L
rm -rf $W && mkdir -p $W && cd $W
cp -r $S/problems/* .
start=$(date +%s.%N)
$S/darcy_thermo_mech-opt -i $IN "$@" > run.log 2>&1
rc=$?
python3 -c "import time;print('EXTWALL %.3f RC $rc'%(time.time()-$start))" >> run.log
