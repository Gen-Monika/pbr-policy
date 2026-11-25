#!/bin/bash
# levels=10 的 K 扫描：验证 r≈58 是否继续放大决策空间与收益。
# 参数与 scan_l5.sh 一致，仅改 PBR_PETSC_LEVELS=10。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=10
export PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/l10
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"

for K in 1 2 3 4 5 6 8; do
  cd "$D" || exit 1
  for R in 1 2 3; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l10_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT"
    interFoam > log.k${K}r${R} 2>&1
    st=$(grep -c '^Time = ' log.k${K}r${R})
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.k${K}r${R} | tail -1 | awk '{print $3}')
    echo "L10 K=$K rep=$R steps=$st et=${et}s"
  done
done

# 大年龄（永不重建，为在线策略提供长年龄曲线）
for R in 1 2; do
  cd "$D" || exit 1
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
  rm -rf 0 && cp -r 0.orig 0
  blockMesh > log.bm 2>&1 && setFields > log.sf 2>&1
  export PBR_PETSC_FREEZE_K=100000
  export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l10_big_r${R}.csv
  rm -f "$PBR_PETSC_OUT"
  interFoam > log.big${R} 2>&1
  echo "L10 BIG rep=$R done"
done
echo "L10_ALL_DONE"
