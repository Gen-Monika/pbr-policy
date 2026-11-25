#!/bin/bash
# lamrun.sh <label> <nstep_max> <bin: orig|pbr> [ENV=VAL ...]
# Runs the official LaMEM Rifting2D_MultigridSolver.dat (only nstep_max may be lowered for smoke tests).
export PATH=/root/miniconda3/bin:$PATH HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml OMP_NUM_THREADS=1
L=$1; N=$2; B=$3; shift 3
SRC=/root/autodl-tmp/envs/lamem/src
O=$SRC/examples/BuiltInSetups/Rifting2D_MultigridSolver.dat
W=/root/autodl-tmp/PBR/lamem_cases/runs/$L
rm -rf $W && mkdir -p $W && cd $W
sed "s/^\(\s*nstep_max\s*=\s*\)[0-9]*/\1$N/" $O > case.dat
diff $O case.dat > case.diff
if [ $B = orig ]; then EXE=$SRC/bin/opt/LaMEM.orig; else EXE=$SRC/bin/opt/LaMEM; fi
for kv in "$@"; do export "$kv"; done
export PBR_LOG=$W/pbr.csv
start=$(date +%s.%N)
$EXE -ParamFile case.dat -log_view > run.log 2>&1
rc=$?
python3 -c "import time;print('EXTWALL %.3f RC $rc'%(time.time()-$start))" >> run.log
# VTK visualisation output (Timestep_*, *.pvd) is kept in full (official nstep_out).
