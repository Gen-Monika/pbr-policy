#!/bin/sh
# A2 步骤 1：在线策略的安全性预检
#   - 只跑前若干步，确认不崩、快照读写正确、决策日志正常
#   - 与离线期望的决策序列对比
# ⚠️ 不用 set -e（配合 source bashrc 会立即退出）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export OMP_NUM_THREADS=1
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

CASE=/root/autodl-tmp/PBR/l20_online
SRC=/root/autodl-tmp/PBR/l20
STORE=/root/autodl-tmp/PBR/online_frozen
OUT=/root/autodl-tmp/PBR/a2_onl

rm -rf $CASE $STORE
mkdir -p $CASE $STORE

# 从 l20 的已收敛算例复制骨架（复用之前 K 扫描用的同一套 case 结构）
cp -a $SRC/system $SRC/constant $SRC/0.orig $CASE/ 2>/dev/null
[ -d "$SRC/0" ] && cp -a $SRC/0 $CASE/ 2>/dev/null

cd $CASE

# ---- 关键配置 ----
foamDictionary -entry startTime -set 0 system/controlDict
foamDictionary -entry endTime   -set 0.1 system/controlDict    # 预检：只跑到 0.1
# 注意：foamDictionary 会重设 LD_LIBRARY_PATH，必须重新导出
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

grep -c . system/controlDict > /dev/null
echo "=== controlDict 关键项 ==="
foamDictionary -entry startTime -value system/controlDict
foamDictionary -entry endTime   -value system/controlDict
echo "=== libs ==="
foamDictionary -entry libs -value system/controlDict

# 压力求解器：PETScILU（与 l20 扫描一致）
echo "=== fvSolution p_rgh 求解器 ==="
grep -A6 "p_rgh" system/fvSolution | head -20

# ---- 在线策略环境变量 ----
export PBR_PETSC_KIND=ilu
export PBR_PETSC_LEVELS=20
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=50
export PBR_PETSC_OUT=${OUT}_sv.csv
export PBR_PETSC_STORE=$STORE
export PBR_PETSC_ONLINE=1
export PBR_PETSC_ONLINE_BASE=100
export PBR_PETSC_ONLINE_OUT=${OUT}_onl.csv
unset PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_BASE

rm -f ${OUT}_sv.csv ${OUT}_onl.csv
setsid nohup interFoam > log.a2ong 2>&1 < /dev/null &
echo "started pid=$!"
