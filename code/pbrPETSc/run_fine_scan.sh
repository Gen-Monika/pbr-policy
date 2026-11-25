#!/bin/bash
# ★★ fine 网格（9072 单元）的 K 扫描
# levels=20 固定（r=110.6），K 覆盖 1..13，5 轮，交错协议。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

export PBR_PETSC_LEVELS=${LC:-20}
NROUND=${NROUND:-5}
KS=${KS:-"1 2 3 5 8 13"}
TAG=${TAG:-fine}

D=/root/autodl-tmp/PBR/${TAG}run
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done
rm -f log.*

# 网格加密 2x（每方向）⇒ 9072 单元
/root/miniconda3/bin/python /root/autodl-tmp/PBR/refine_mesh.py "$D/system/blockMeshDict" 2

rm -rf 0 constant/polyMesh && cp -r 0.orig 0
blockMesh > log.bm 2>&1
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
echo FINE_DONE
