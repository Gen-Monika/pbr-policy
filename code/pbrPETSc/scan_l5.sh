#!/bin/bash
# ILU(5) 的 K 扫描：验证高填充层级是否真的放大决策空间。
# 参数与 scan.sh 相同，只改 PBR_PETSC_LEVELS。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=5
export PBR_PETSC_BENCH=1 PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D5=/root/autodl-tmp/PBR/l5
rm -rf $D5 && cp -r /root/autodl-tmp/PBR/damBreak_petsc $D5

for K in 1 2 3 4 5 6 8; do
  cd $D5
  for R in 1 2 3; do
    # 清理时间目录（严格有界，绝不碰 0.orig）
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l5_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT"
    interFoam > log.k${K}r${R} 2>&1
    st=$(grep -c '^Time = ' log.k${K}r${R})
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.k${K}r${R} | tail -1 | awk '{print $3}')
    echo "L5 K=$K rep=$R steps=$st et=${et}s"
  done
done

# 大年龄（永不重建）
cd $D5
for R in 1 2; do
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
  rm -rf 0 && cp -r 0.orig 0
  blockMesh > log.bm 2>&1 && setFields > log.sf 2>&1
  export PBR_PETSC_FREEZE_K=100000
  export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l5_big_r${R}.csv
  rm -f "$PBR_PETSC_OUT"
  interFoam > log.big${R} 2>&1
  echo "L5 BIG rep=$R done"
done
echo "L5_ALL_DONE"
