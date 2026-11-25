#!/bin/bash
# ★ 严格交错墙钟实验（levels=5）：K=1 vs K=2 vs K=3，交替进行，取中位。
#
# 这是此前失败过的实验的正确重做版本：
#   - 旧实验的致命错误是「成组运行」（每个 K 连续跑完再换下一个），
#     机器状态漂移会被误读成 K 的差异。
#   - 正确做法：每一轮里轮流跑 K=1/2/3，重复 5 轮，取每个 K 的中位。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=5
export PBR_PETSC_BENCH=0
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

D=/root/autodl-tmp/PBR/l5wt
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for R in 1 2 3 4 5; do
  for K in 1 2 3; do
    for d in */; do
      d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/l5wt_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT"
    S=$(date +%s)
    interFoam > log.r${R}k${K} 2>&1
    E=$(date +%s)
    wall=$((E - S))
    st=$(grep -c '^Time = ' log.r${R}k${K})
    echo "round=$R K=$K wall=${wall}s steps=$st"
  done
done
echo "WALLTEST_DONE"
