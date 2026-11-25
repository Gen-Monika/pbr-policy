#!/bin/bash
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
cd /root/autodl-tmp/PBR/stefan || exit 1
sed -i "s|^endTime.*|endTime         20;|" system/controlDict
export PBR_PETSC_KIND=ilu PBR_PETSC_BENCH=1 PBR_PETSC_REPS=6
export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=50 PBR_PETSC_FREEZE_K=3
export PBR_PETSC_NNZ=1
for LV in 0 1 2 3 5 8 10; do
  [ -f /root/autodl-tmp/PBR/st_lv${LV}.csv ] && [ -s /root/autodl-tmp/PBR/st_lv${LV}.csv ] && { echo "LV=$LV 已完成，跳过"; continue; }
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing|1.36) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
  export PBR_PETSC_LEVELS=$LV
  export PBR_PETSC_OUT=/root/autodl-tmp/PBR/st_lv${LV}.csv
  rm -f $PBR_PETSC_OUT
  ST=$(date +%s%3N); timeout 400 interCondensatingEvaporatingFoam > log.lv${LV} 2>&1; EN=$(date +%s%3N)
  echo "LV=$LV wall=$(( (EN-ST)/1000 ))s nSolve=$(grep -c "Solving for p_rgh" log.lv${LV})"
  grep -m1 "PETSc ilu" log.lv${LV}
  grep -m1 PBR_NNZ log.lv${LV}
done
echo ST_LV_DONE
