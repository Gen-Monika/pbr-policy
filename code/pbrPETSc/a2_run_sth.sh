#!/bin/bash
# ★★★ A2-sth：sth 的 C++ 在线验证（第一层：把在线验证扩到 7/7，先跑有争议的 sth）
#
# ═══════════════════════════════════════════════════════════════════════
# 为什么要跑这个
# ═══════════════════════════════════════════════════════════════════════
# A=9 补测发现：sth 的老化尾部在 a≈6 饱和，形状迁移的单调延长高估了它
# +4.5%~+13.6%，把最优策略从"91 次重建"翻转成"974 次重建"。
# ⇒ sth 的模型预测【最不可信】，必须用实测裁决：
#     若实测给 ~970 次重建  ⇒ 实测推翻了"饱和"结论（外推反而是对的）
#     若实测给 接近 91      ⇒ 饱和结论成立，外推错
#
# ═══════════════════════════════════════════════════════════════════════
# 与 a2_run_v2.sh 的差异（sth 特有，全部照搬 a_phase_scan.sh 已验证的处理）
# ═══════════════════════════════════════════════════════════════════════
#   BASE = 50        （不是 100；sth 的 B0 是 50）
#   SRC  = stefan    （不是 damBreak_petsc）
#   求解器 = interCondensatingEvaporatingFoam
#   起始目录 = 1.36  （sth 特有：从 1.36 重开，需 setAlphaField）
#   LEVELS = 5
#
# 用法：MODES="ONLs" NROUND=3 TAG=a2sth bash a2_run_sth.sh
#
# ⚠️ 不用 set -e（OpenFOAM 的 bashrc 末条命令返回 1）
# ⚠️ 固定周期组必须同时设 FREEZE_AT
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

export PBR_PETSC_KIND=ilu
export PBR_PETSC_LEVELS=${LEVELS:-5}
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

NROUND=${NROUND:-3}
MODES=${MODES:-"ONLs"}
TAG=${TAG:-a2sth}
LVL=${LVL:-last}
SRC=${SRC:-/root/autodl-tmp/PBR/stefan}
BASE=${BASE:-50}          # ★ sth 的 B0 是 50
P=/root/autodl-tmp/PBR
D=$P/${TAG}_case
STORE=$P/${TAG}_store

rm -rf "$D" "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D"; cd "$D" || exit 1

# sth 的 endTime 固定为 20（与相位扫描一致；源里可能是 100）
foamDictionary system/controlDict -entry endTime -set 20 > /dev/null 2>&1

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|1.36|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

echo "=== $TAG/sth 开始 $(date '+%F %T')  MODES=[$MODES] NROUND=$NROUND LEVELS=$PBR_PETSC_LEVELS BASE=$BASE SRC=$SRC ==="
for R in $(seq 1 $NROUND); do
  for MODE in $MODES; do
    clean_times
    # ★ sth 特有：从 1.36 重开（需要 setAlphaField 生成 alpha 场）
    rm -rf 1.36; cp -rf 0 1.36; setAlphaField > log.sf 2>&1

    unset PBR_PETSC_ONLINE PBR_PETSC_ONLINE_RCOST PBR_PETSC_ONLINE_LVL PBR_PETSC_ONLINE_OUT
    unset PBR_PETSC_ONLINE_DMODE PBR_PETSC_ONLINE_DMINN
    unset PBR_PETSC_FREEZE_K PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_BASE
    rm -f "$STORE"/*.bin
    case $MODE in
      K*)   export PBR_PETSC_FREEZE_AT=1 PBR_PETSC_FREEZE_BASE=$BASE PBR_PETSC_FREEZE_K=${MODE#K} ;;
      ONLs) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=$BASE PBR_PETSC_ONLINE_RCOST=solve PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
      ONLp) export PBR_PETSC_ONLINE=1 PBR_PETSC_ONLINE_BASE=$BASE PBR_PETSC_ONLINE_RCOST=step  PBR_PETSC_ONLINE_LVL=$LVL
            export PBR_PETSC_ONLINE_DMODE=extrap PBR_PETSC_ONLINE_DMINN=1 ;;
    esac
    [ -n "$PBR_PETSC_ONLINE" ] && export PBR_PETSC_ONLINE_OUT=$P/${TAG}_onl_${MODE}_r${R}.csv && rm -f $PBR_PETSC_ONLINE_OUT
    export PBR_PETSC_STORE=$STORE
    export PBR_PETSC_OUT=$P/${TAG}_pc_${MODE}_r${R}.csv
    export PBR_SOLVER_OUT=$P/${TAG}_sv_${MODE}_r${R}.csv
    rm -f $PBR_PETSC_OUT $PBR_SOLVER_OUT
    S=$(date +%s%3N)
    interCondensatingEvaporatingFoam > log.${MODE}.r${R} 2>&1
    E=$(date +%s%3N)
    et=$(grep -o "ExecutionTime = [0-9.]* s" log.${MODE}.r${R} | tail -1 | awk '{print $3}')
    iters=$(awk '/Solving for p_rgh/{match($0,/No Iterations [0-9]+/); s+=substr($0,RSTART+14,RLENGTH-14)} END{print s+0}' log.${MODE}.r${R})
    nsteps=$(grep -c "^Time = " log.${MODE}.r${R})
    rbsteps=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' $PBR_PETSC_OUT)
    fatal=$(grep -c "FOAM FATAL" log.${MODE}.r${R})
    echo "round=$R mode=$MODE wall_ms=$((E-S)) execTime=$et iters=$iters nsteps=$nsteps rbsteps=$rbsteps fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg)"
  done
done
echo "=== $TAG 结束 $(date '+%F %T') ==="
echo "${TAG}_DONE"
