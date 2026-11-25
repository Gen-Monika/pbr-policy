#!/bin/bash
# 单次 hotRoom 运行：参数 K R
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
K=$1; R=$2
export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=6 PBR_PETSC_LEVELS=5
export OMP_NUM_THREADS=1
D=/root/autodl-tmp/PBR/hotRoom
cd "$D" || exit 1
for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -rf 0 && cp -r 0.orig 0
blockMesh > log.bm 2>&1
export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=100 PBR_PETSC_FREEZE_K=$K
export PBR_PETSC_OUT=/root/autodl-tmp/PBR/hr_pc_k${K}_r${R}.csv
export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/hr_sv_k${K}_r${R}.csv
rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
ST=$(date +%s%3N)
buoyantPimpleFoam > log.r${R}k${K} 2>&1
EN=$(date +%s%3N)
et=$(grep -o "ExecutionTime = [0-9.]* s" log.r${R}k${K} | tail -1 | awk "{print \$3}")
sv=$(grep -o "totalSolveTime=[0-9.eE+-]*" log.r${R}k${K} | tail -1 | cut -d= -f2)
echo "round=$R K=$K wall_ms=$((EN-ST)) execTime=${et} solveTime=${sv} nStep=$(grep -c "^Time = " log.r${R}k${K}) nSolve=$(grep -c "Solving for p_rgh" log.r${R}k${K})" >> /root/autodl-tmp/PBR/hr_scan.out
