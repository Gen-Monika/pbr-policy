#!/bin/bash
# ★★ 消融实验：快照写入的 I/O 是否解释了"未解释开销"？
#
# 背景：K=1 写 344 个快照（每个 87 KB），K=3 只写 181 个。
#       而 tFreeze 只计了 fwrite 调用本身（0.078 s vs 0.026 s）。
#       若磁盘 I/O 的真实成本远高于计时值，则墙钟会出现"未解释"的差额。
#
# 做法：把 PBR_PETSC_STORE 从 xfs 的 /root/autodl-tmp 改到内存盘 /dev/shm，
#       重跑 K=1 与 K=3。若两者的墙钟差显著缩小，则 I/O 是主因。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=10
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=100
export OMP_NUM_THREADS=1

# 内存盘
SHM=/dev/shm/pbr_snap
mkdir -p $SHM

D=/root/autodl-tmp/PBR/ablation
rm -rf "$D" && cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

for R in 1 2 3; do
  for K in 1 3; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    rm -rf $SHM/* 2>/dev/null
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_STORE=$SHM
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/abl_shm_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT"
    S=$(date +%s%3N)
    interFoam > log.shm${R}k${K} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.shm${R}k${K} | tail -1 | awk '{print $3}')
    echo "STORE=shm round=$R K=$K wall_ms=${wall} execTime=${et}"
  done
done

# 对照：写回 xfs（同一批参数，交替进行以避免状态漂移）
for R in 1 2 3; do
  for K in 1 3; do
    for d in */; do d=${d%/}
      case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
      if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
    done
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_STORE=/root/autodl-tmp/PBR/xfs_snap
    export PBR_PETSC_OUT=/root/autodl-tmp/PBR/abl_xfs_k${K}_r${R}.csv
    rm -rf /root/autodl-tmp/PBR/xfs_snap
    rm -f "$PBR_PETSC_OUT"
    S=$(date +%s%3N)
    interFoam > log.xfs${R}k${K} 2>&1
    E=$(date +%s%3N)
    wall=$((E - S))
    et=$(grep -o 'ExecutionTime = [0-9.]* s' log.xfs${R}k${K} | tail -1 | awk '{print $3}')
    echo "STORE=xfs round=$R K=$K wall_ms=${wall} execTime=${et}"
  done
done
echo "ABLATION_DONE"
