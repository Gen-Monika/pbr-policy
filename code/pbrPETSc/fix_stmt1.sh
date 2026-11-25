#!/bin/bash
# 补跑 ITEM1 被 ITEM2 覆盖的 12 次（k1/k3/k5/k8 × r1..r3, endTime=20）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
cd /root/autodl-tmp/PBR/stefan || exit 1
sed -i "s|^endTime.*|endTime         20;|" system/controlDict
export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=6 PBR_PETSC_LEVELS=5
export OMP_NUM_THREADS=1
# 先把被覆盖的 4 个完好档位（k2/k13）备份
cd /root/autodl-tmp/PBR
mkdir -p _keep_k2k13
for K in 2 13; do for R in 1 2 3; do
  cp -f sth_pc_k${K}_r${R}.csv _keep_k2k13/ 2>/dev/null
done; done
echo "已备份 k2/k13: $(ls _keep_k2k13 | wc -l) 个"
cd /root/autodl-tmp/PBR/stefan || exit 1
for R in 1 2 3; do
  for K in 1 3 5 8; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing|1.36) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=50 PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/sth_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/sth_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
    timeout 600 interCondensatingEvaporatingFoam > log.r${R}k${K} 2>&1
  done
done
cd /root/autodl-tmp/PBR
# 恢复 k2/k13（重跑过程会清空 run 目录但其 CSV 在 PBR 根目录，未被动过）
echo FIX_STH_DONE
