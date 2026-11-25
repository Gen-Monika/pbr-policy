#!/bin/bash
# ★ Stefan endTime=100（界面在 88.4% 处，仍在域内）
#   K∈{1,5,8,13,20} × 3 轮，整批重跑含自带 K=1 基线
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=6 PBR_PETSC_LEVELS=5
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/stefan
cd "$D" || exit 1
sed -i "s|^endTime.*|endTime         100;|" system/controlDict
grep -E "^endTime" system/controlDict

for R in 1 2 3; do
  for K in 1 5 8 13 20; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing|1.36) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=50 PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/st100_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/st100_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    ST=$(date +%s%3N)
    timeout 1800 interCondensatingEvaporatingFoam > log.r${R}k${K} 2>&1
    EN=$(date +%s%3N)
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.r${R}k${K} | tail -1 | awk "{print \$3}")
    echo "round=$R K=$K wall_ms=$((EN-ST)) execTime=${et} nStep=$(grep -c "^Time = " log.r${R}k${K}) nSolve=$(grep -c "Solving for p_rgh" log.r${R}k${K})"
  done
done
echo ST100_DONE
