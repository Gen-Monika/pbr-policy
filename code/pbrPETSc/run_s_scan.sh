#!/bin/bash
# ★★ s（=nCorrectors）可变扫描：验证判据阈值 r/s 决定最优 K
# levels 固定（默认 10），只改 nCorrectors ⇒ r 必须不变，最优 K 应随 r/s 移动。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

LC=${LC:-10}
NC=${NC:-1 2 3}
KS=${KS:-"1 2 3 4 5 6 8 10"}
NROUND=${NROUND:-5}
TAG=${TAG:-s}

D=/root/autodl-tmp/PBR/${TAG}run
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

export PBR_PETSC_LEVELS=$LC

for S in $NC; do
  foamDictionary system/fvSolution -entry PIMPLE.nCorrectors -set $S
  echo "### nCorrectors=$S Levels=$LC"
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
      export PBR_PETSC_OUT=/root/autodl-tmp/PBR/${TAG}_pc_s${S}_k${K}_r${R}.csv
      export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/${TAG}_sv_s${S}_k${K}_r${R}.csv
      rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
      ST=$(date +%s%3N)
      interFoam > log.s${S}r${R}k${K} 2>&1
      EN=$(date +%s%3N)
      wall=$((EN - ST))
      et=$(grep -o "ExecutionTime = [0-9.]* s" log.s${S}r${R}k${K} | tail -1 | awk "{print \$3}")
      sv=$(grep -o "totalSolveTime=[0-9.eE+-]*" log.s${S}r${R}k${K} | tail -1 | cut -d= -f2)
      ns=$(grep -c "Solving for p_rgh" log.s${S}r${R}k${K})
      nt=$(grep -c "^Time = " log.s${S}r${R}k${K})
      echo "s=$S round=$R K=$K wall_ms=${wall} execTime=${et} solveTime=${sv} nSolve=${ns} nStep=${nt}"
    done
  done
done
echo S_SCAN_DONE
