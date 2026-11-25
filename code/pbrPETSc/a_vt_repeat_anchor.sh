#!/bin/bash
# 单锚点重复运行（verification of determinism in the aging region)
#
# 目的：OpenFOAM 相位扫描本身没有重复运行，"同一锚点跑两遍、老化区逐位相同"
# 这个最直接的对照缺失。本脚本重跑 fx 的 B=100 锚点（K=7，与 phs_fx_B100_K7_r1
# 完全相同的参数），输出到独立 TAG=phsvt，不复用任何已有 store/目录。
#
# 参数来源：a_phase_scan.sh 的 fx 分支 LVL=10 SRC=$P/fixed DEF_B0=100，
# 以及 PBR_PETSC_REPS=8 / PBR_PETSC_KIND=ilu 两项环境设置。
#
# 判据：与 phs_fx_B100_K7_r1.csv 逐 (timeIndex,reusedFrom) 比对 N(t,a) 是否逐位相同。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

P=/root/autodl-tmp/PBR
NAME=fx; LVL=10; SRC=$P/fixed; PFX=fx; SOLVER=interFoam
TAG=phsvt; B=100; K=7; R=2
D=$P/${TAG}_${NAME}; STORE=$P/${TAG}_store_${NAME}

rm -rf "$D" "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D" || { echo "!! copy failed"; exit 1; }
cd "$D" || exit 1

for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]] && rm -rf -- "$d"
done

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null 2>&1
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null 2>&1
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null 2>&1

echo "=== $TAG/$NAME 单锚点重复运行开始 $(date '+%F %T')  B=$B K=$K R=$R levels=$LVL ==="

rm -rf 0 && cp -r 0.orig 0
blockMesh > log.bm 2>&1
setFields > log.sf 2>&1

unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN
export PBR_PETSC_LEVELS=$LVL
export PBR_PETSC_FREEZE_AT=1
export PBR_PETSC_FREEZE_BASE=$B
export PBR_PETSC_FREEZE_K=$K
export PBR_PETSC_STORE=$STORE
OUT=$P/${TAG}_${PFX}_B${B}_K${K}_r${R}.csv
export PBR_PETSC_OUT=$OUT
export PBR_SOLVER_OUT=$P/${TAG}_${PFX}_B${B}_K${K}_sv_r${R}.csv
rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT" "$STORE"/*.bin

LOG=log.B${B}K${K}_r${R}
S=$(date +%s%3N)
timeout 7200 $SOLVER > $LOG 2>&1
E=$(date +%s%3N)

fatal=$(grep -c "FOAM FATAL" $LOG)
nsteps=$(grep -c "^Time = " $LOG)
nuniq=$(awk -F, '{c[$1]=1} END{print length(c)}' "$OUT" 2>/dev/null)
lv=$(head -1 "$OUT" 2>/dev/null | cut -d, -f4)
echo "$NAME B=$B K=$K R=$R wall_ms=$((E-S)) nsteps=$nsteps csvuniq=$nuniq levels=$lv fatal=$fatal"
echo "out=$OUT"
echo "=== 结束 $(date '+%F %T') ==="
