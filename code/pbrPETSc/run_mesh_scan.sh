#!/bin/bash
# 通用扫描：网格加密倍率 × levels × K 集合 × 轮数
#   MESH_DV  网格加密倍率（1=2268, 2=9072, 3=20412）
#   LC       levels
#   KS       K 列表
#   NROUND   轮数
#   TAG      输出前缀
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export PBR_PETSC_LEVELS=${LC:-20}
export OMP_NUM_THREADS=1

MESH_DV=${MESH_DV:-2}
KS=${KS:-"1 2 3 5 8"}
NROUND=${NROUND:-3}
TAG=${TAG:-scan}

D=/root/autodl-tmp/PBR/${TAG}run
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -f log.*

if [ "$MESH_DV" != "1" ]; then
  /root/miniconda3/bin/python /root/autodl-tmp/PBR/refine_mesh.py "$D/system/blockMeshDict" "$MESH_DV"
fi

rm -rf 0 constant/polyMesh && cp -r 0.orig 0
blockMesh > log.bm 2>&1
grep -iE "nCells:" log.bm | tail -1
setFields > log.sf 2>&1

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG
foamDictionary system/controlDict -entry libs \
  -set "(libpbrSolverTimer.so libpbrPETSc.so)"

for R in $(seq 1 $NROUND); do
  for K in $KS; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/${TAG}_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/${TAG}_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    ST=$(date +%s%3N)
    interFoam > log.r${R}k${K} 2>&1
    EN=$(date +%s%3N)
    wall=$((EN - ST))
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.r${R}k${K} | tail -1 | awk "{print \$3}")
    sv=$(grep -o "totalSolveTime=[0-9.eE+-]*" log.r${R}k${K} | tail -1 | cut -d= -f2)
    ns=$(grep -c "Solving for p_rgh" log.r${R}k${K})
    nt=$(grep -c "^Time = " log.r${R}k${K})
    echo "round=$R K=$K wall_ms=${wall} execTime=${et} solveTime=${sv} nSolve=${ns} nStep=${nt}"
  done
done
echo SCAN_DONE
