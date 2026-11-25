#!/bin/bash
# ★★ solve() 层面的计时实验：K=1 / K=3 / K=8，闭合预算
#
# 目的：此前的"未解释 8-11 s"疑为 CG 主循环（Amul/gSumProd/向量更新）的开销，
#       因为 PBR_PETSc 的计时只覆盖预条件子内部。
#       本实验用 PBRPCG（PCG 的计时间包装）在 scalarSolve 层面测量
#       压力求解的总耗时，从而闭合预算。
#
# 关键：PBRPCG 继承 PCG，注册为新的 solver 名，不改 OpenFOAM 源码。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=10
export PBR_PETSC_BENCH=1          # 同时打开预条件子内部计时，便于对照
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/stwt
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

# 准备算例：把 p_rgh 与 p_rghFinal 都换成 PBRPCG
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

for R in 1 2 3; do
  for K in 1 3 8; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/stwt_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/stwt_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    S=$(date +%s%3N)
    interFoam > log.r${R}k${K} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.r${R}k${K} | tail -1 | awk '{print $3}')
    sv=$(grep -o 'totalSolveTime=[0-9.eE+-]*' log.r${R}k${K} | tail -1)
    echo "round=$R K=$K wall_ms=${wall} execTime=${et} ${sv}"
  done
done
echo "STWT_DONE"
