#!/bin/bash
# A2 步骤 1：在线策略的在线预检（短程，约 120 步）
#
# 目的（三项，缺一不可）：
#   1. 不崩：快照读写、PC 复用路径在在线决策下正常工作
#   2. 决策序列合理：预热期 100 步全重建，之后按判据决策
#   3. 与离线期望一致：日志里的迭代数/年龄序列能与离线模拟对照
#
# 说明：本脚本从 damBreak_petsc 复制骨架（与 l20 / l15 扫描完全相同的做法），
#       保证与已有 K 扫描结果同源可比。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=20
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8
export OMP_NUM_THREADS=1

# ★ 在线策略
export PBR_PETSC_ONLINE=1
export PBR_PETSC_ONLINE_BASE=100
unset PBR_PETSC_FREEZE_K
unset PBR_PETSC_FREEZE_AT
unset PBR_PETSC_FREEZE_BASE

STORE=/root/autodl-tmp/PBR/onl_store_pre
D=/root/autodl-tmp/PBR/onl_pre
rm -rf "$STORE" "$D"
mkdir -p "$STORE"
cp -r /root/autodl-tmp/PBR/damBreak_petsc "$D"
cd "$D" || exit 1

# 清理时间目录（⚠️ 不能用 rm -rf 0 [0-9]* —— 会误删 0.orig）
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
foamDictionary system/controlDict -entry endTime -set 0.36

# ⚠️ foamDictionary 会重设 LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_STORE=$STORE
export PBR_PETSC_OUT=/root/autodl-tmp/PBR/onl_pre_sv.csv
export PBR_PETSC_ONLINE_OUT=/root/autodl-tmp/PBR/onl_pre_onl.csv
export PBR_SOLVER_OUT=/root/autodl-tmp/PBR/onl_pre_solver.csv
rm -f $PBR_PETSC_OUT $PBR_PETSC_ONLINE_OUT $PBR_SOLVER_OUT

echo "=== 配置确认 ==="
echo "endTime       = $(foamDictionary -entry endTime -value system/controlDict)"
echo "ONLINE        = $PBR_PETSC_ONLINE"
echo "ONLINE_BASE   = $PBR_PETSC_ONLINE_BASE"
echo "LEVELS        = $PBR_PETSC_LEVELS"
echo "libs          = $(foamDictionary -entry libs -value system/controlDict)"

S=$(date +%s%3N)
interFoam > log.onl_pre 2>&1
E=$(date +%s%3N)
echo "wall_ms=$((E - S))"
et=$(grep -o "ExecutionTime = [0-9.]* s" log.onl_pre | tail -1 | awk '{print $3}')
echo "execTime=$et"
echo "=== 步数 ==="; grep -c "^Time = " log.onl_pre
echo "=== 快照文件数 ==="; ls "$STORE" | wc -l
echo "PRE_DONE"
