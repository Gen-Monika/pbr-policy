#!/bin/bash
# hotRoom（buoyantPimpleFoam, 4000 单元, 3D, s=2）的 K 扫描
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

LC=${LC:-5}
KS=${KS:-"1 2 3 5 8"}
NROUND=${NROUND:-3}
TAG=hr

export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=6
export PBR_PETSC_LEVELS=$LC
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/hotRoom
cd "$D" || exit 1

for R in $(seq 1 $NROUND); do
  for K in $KS; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    export PBR_PETSC_FREEZE_AT=1
    export PBR_PETSC_FREEZE_BASE=100
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/${TAG}_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/${TAG}_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    ST=$(date +%s%3N)
    buoyantPimpleFoam > log.r${R}k${K} 2>&1
    EN=$(date +%s%3N)
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.r${R}k${K} | tail -1 | awk "{print \$3}")
    sv=$(grep -o "totalSolveTime=[0-9.eE+-]*" log.r${R}k${K} | tail -1 | cut -d= -f2)
    echo "round=$R K=$K wall_ms=$((EN-ST)) execTime=${et} solveTime=${sv} nStep=$(grep -c "^Time = " log.r${R}k${K}) nSolve=$(grep -c "Solving for p_rgh" log.r${R}k${K})"
  done
done
echo HR_DONE
