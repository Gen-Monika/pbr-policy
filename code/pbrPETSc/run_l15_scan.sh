#!/bin/bash
# levels=15 的 K 扫描（修正后的 25 列口径）
# 同时打开 PBRPCG（CG 总耗时）与 PBR_PETSc（内部计时）。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=15
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/l15
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -rf 0 && cp -r 0.orig 0
blockMesh > log.bm 2>&1
setFields > log.sf 2>&1

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG
foamDictionary system/controlDict -entry libs \
  -set "(libpbrSolverTimer.so libpbrPETSc.so)"

for R in 1 2 3 4 5; do
  for K in 1 2 3 5 8; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l15_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/l15_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    S=$(date +%s%3N)
    interFoam > log.r${R}k${K} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.r${R}k${K} | tail -1 | awk '{print $3}')
    sv=$(grep -o 'totalSolveTime=[0-9.eE+-]*' log.r${R}k${K} | tail -1 | cut -d= -f2)
    echo "round=$R K=$K wall_ms=${wall} execTime=${et} solveTime=${sv}"
  done
done
echo "L15_DONE"
