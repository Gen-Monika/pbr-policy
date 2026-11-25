#!/bin/bash
# ★★★ 追查"CG 每迭代成本随 K 下降"的异常
#
# 背景（solve() 层面计时的结果）：
#   K=1: CG自身 8.367 s / 7957 迭代 = 1.051 ms/迭代
#   K=3: CG自身 5.420 s / 12527     = 0.433 ms/迭代
#   K=8: CG自身 5.013 s / 35486     = 0.141 ms/迭代
#
# 但 tIter（孤立测量的单次 apply）恒为 146 µs ⇒ 若每迭代成本恒定，
# K=1 的 CG自身 应约 1.16 s，实测 8.367 s（差 7.2 倍）。
#
# 新加的 PBR_PETSc 累加器（静态，跨 1032 个实例）：
#   s_tApplyAccum_ : 真实 CG 循环中 precondition() 的累计耗时
#   s_nApplyCalls_ : 真实调用次数
# ⇒ 二者相除即"真实循环内的每迭代 apply 成本"，
#   可与孤立的 tIter（146 µs）对比。
#
# 同时打开 PBRPCG（solve 层面）以给出 CG 总耗时。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=10
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/applycost
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
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/ac_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/ac_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    S=$(date +%s%3N)
    interFoam > log.r${R}k${K} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.r${R}k${K} | tail -1 | awk '{print $3}')
    sv=$(grep -o 'totalSolveTime=[0-9.eE+-]*' log.r${R}k${K} | tail -1 | cut -d= -f2)
    # 真实 apply 累计与调用次数：取 CSV 最后一行的后两列
    last=$(tail -1 "$PBR_PETSC_OUT")
    ta=$(echo "$last" | awk -F, '{print $(NF-1)}')
    na=$(echo "$last" | awk -F, '{print $NF}')
    echo "round=$R K=$K wall_ms=${wall} execTime=${et} solveTime=${sv} applyAccum=${ta} nApply=${na}"
  done
done
echo "APPLYCOST_DONE"
