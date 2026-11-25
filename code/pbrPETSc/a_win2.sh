#!/bin/bash
# ★★★ 证据链 (b)：给 fx / l20 补第二个时间窗（endTime 1 → 2）
#
# ═══════════════════════════════════════════════════════════════════════
# 为什么这样设计：一批数据给出两个窗口
# ═══════════════════════════════════════════════════════════════════════
# endTime=2 的运行【天然包含】 endTime=1 的全部步（前 344 步），
# 于是同一批 run 同时给出：
#     窗口 1 = [0, 1]   （前段，"溃坝 → 撞击壁面"阶段）
#     窗口 2 = [1, 2]   （后段，"反弹 → 衰减"阶段）
# ⇒ 两段来自【同一次求解、同一轮】，排除了跨批次/跨机器的噪声，
#   这对"K* 是否随演化阶段移动"这个问题是决定性的。
#
# ═══════════════════════════════════════════════════════════════════════
# 与既有 Stefan 三窗的关系
# ═══════════════════════════════════════════════════════════════════════
# Stefan 已证 K* 随窗口移动：endTime=20 → K=5；50/100 → K=8–13。
# 但 Stefan 是【慢漂移、低 ρ】的配置。本脚本检验：
#   damBreak 系（fx 快漂移、l20 中等）是否也有跨窗口的 K* 移动。
# 这是"免扫描"贡献能否成立的关键证据。
#
# ═══════════════════════════════════════════════════════════════════════
# 参数
# ═══════════════════════════════════════════════════════════════════════
#   B0 = 100（与既有 fx/l20 实验一致，保持周期相位可比）
#   K ∈ {1,2,3,4,5,6}（覆盖两侧窗口在不同 ρ 下可能出现的最优）
#   3 轮，同轮交错
#
# 用法：NAME=fx TAG=w2fx bash a_win2.sh
#       NAME=l20 TAG=w2l20 bash a_win2.sh
#
# ⚠️ 不用 set -e（OpenFOAM bashrc 末条命令返回 1）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

P=/root/autodl-tmp/PBR
NAME=${NAME:?必须给 NAME}
case "$NAME" in
  fx)  LVLD=10 SRC=$P/fixed ;;
  l20) LVLD=20 SRC=$P/l20   ;;
  *) echo "未知 NAME=$NAME"; exit 1 ;;
esac
LEVELS=${LEVELS:-$LVLD}
BASE=${BASE:-100}
ENDT=${ENDT:-2}
NROUND=${NROUND:-3}
MODES=${MODES:-"K1 K2 K3 K4 K5 K6"}
TAG=${TAG:-w2$NAME}
D=$P/${TAG}_case
STORE=$P/${TAG}_store

rm -rf "$D" "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D"; cd "$D" || exit 1

# ★ 延长到 endTime=2（官方 tutorial 是 1；这是本项目既有的"多时间窗"做法，
#   与 Stefan 的 20/50/100 同类）
foamDictionary system/controlDict -entry endTime -set $ENDT > /dev/null 2>&1
foamDictionary system/controlDict -entry writeInterval -set 1 > /dev/null 2>&1

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

export PBR_PETSC_KIND=ilu
export PBR_PETSC_LEVELS=$LEVELS
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

echo "=== $TAG/$NAME 开始 $(date '+%F %T')  MODES=[$MODES] NROUND=$NROUND endTime=$ENDT BASE=$BASE LEVELS=$LEVELS ==="
for R in $(seq 1 $NROUND); do
  for MODE in $MODES; do
    clean_times; rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1; setFields > log.sf 2>&1
    unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL PBR_PETSC_ONLINE_OUT
    unset PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN
    unset PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin
    K=${MODE#K}
    export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=$BASE PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_STORE=$STORE
    export PBR_PETSC_OUT=$P/${TAG}_pc_${MODE}_r${R}.csv
    export PBR_SOLVER_OUT=$P/${TAG}_sv_${MODE}_r${R}.csv
    rm -f $PBR_PETSC_OUT $PBR_SOLVER_OUT
    S=$(date +%s%3N)
    timeout 7200 interFoam > log.${MODE}.r${R} 2>&1
    E=$(date +%s%3N)
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.${MODE}.r${R} | tail -1 | awk '{print $3}')
    iters=$(awk '/Solving for p_rgh/{match($0,/No Iterations [0-9]+/); s+=substr($0,RSTART+14,RLENGTH-14)} END{print s+0}' log.${MODE}.r${R})
    nsteps=$(grep -c "^Time = " log.${MODE}.r${R})
    rbsteps=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' $PBR_PETSC_OUT)
    fatal=$(grep -c "FOAM FATAL" log.${MODE}.r${R})
    echo "round=$R mode=$MODE K=$K wall_ms=$((E-S)) execTime=$et iters=$iters nsteps=$nsteps rbsteps=$rbsteps fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg)"
  done
done
echo "=== $TAG 结束 $(date '+%F %T') ==="
echo "${TAG}_DONE"
