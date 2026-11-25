#!/bin/bash
# ★ Stefan 的 K 扫描（interCondensatingEvaporatingFoam, 800 单元, s=4, levels=5, r≈16.7）
#   endTime=20（约 52s/次），K∈{1,2,3,5,8} × 3 轮
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

LC=${LC:-5}
KS=${KS:-"1 2 3 5 8"}
NROUND=${NROUND:-3}
ET=${ET:-20}
TAG=${TAG:-sth}

export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=6
export PBR_PETSC_LEVELS=$LC
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/stefan
cd "$D" || exit 1
sed -i "s|^endTime.*|endTime         $ET;|" system/controlDict

for R in $(seq 1 $NROUND); do
  for K in $KS; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing|1.36) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    export PBR_PETSC_FREEZE_AT=1
    export PBR_PETSC_FREEZE_BASE=50
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/${TAG}_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/${TAG}_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    ST=$(date +%s%3N)
    timeout 900 interCondensatingEvaporatingFoam > log.r${R}k${K} 2>&1
    EN=$(date +%s%3N)
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.r${R}k${K} | tail -1 | awk "{print \$3}")
    echo "round=$R K=$K wall_ms=$((EN-ST)) execTime=${et} nStep=$(grep -c "^Time = " log.r${R}k${K}) nSolve=$(grep -c "Solving for p_rgh" log.r${R}k${K})"
  done
done
echo ST_DONE
