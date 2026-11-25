#!/bin/bash
# ★★★ A-补实验：把 K 扫描上限推到最优 K* 的 4–6 倍，消除"边界外推"
#
# 为什么要补（见 a_oracle_fixed_and_coverage_gap §5）：
#   现有各配置的 K 上限只有 5–13，而最优 K* 是 2–6 ⇒ 只有 1–3 倍余量。
#   于是"最优周期 vs 每步重建"的对比有一侧落在【没有实测的年龄】区，
#   导致插值口径（step vs linear）能改变 regret 达 25–60 pp。
#
# 本脚本对 fx(L10) 与 l20(L20) 补扫 K ∈ {13, 20, 30}，3 轮。
# 与已有的 K ∈ {1,2,3,5,8} 合并后，年龄覆盖达 30，是 K* 的 5–15 倍。
#
# ⚠️ 固定周期组必须同时设 PBR_PETSC_FREEZE_AT（否则退化为 K=1，已踩过两次）
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1

export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

NROUND=${NROUND:-3}
KS=${KS:-"13 20 30"}
P=/root/autodl-tmp/PBR
TAG=${TAG:-covscan}

# 算例骨架：l20 与 fx 都源自 damBreak_petsc，仅 levels 不同
run_one() {
  local LVL=$1 D=$2 K=$3 R=$4
  cd "$D" || return 1
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done
  rm -rf 0 && cp -r 0.orig 0
  blockMesh > log.bm 2>&1
  setFields > log.sf 2>&1
  unset PBR_PETSC_ONLINE
  export PBR_PETSC_LEVELS=$LVL
  export PBR_PETSC_FREEZE_AT=1
  export PBR_PETSC_FREEZE_BASE=100
  export PBR_PETSC_FREEZE_K=$K
  export PBR_PETSC_STORE=$P/${TAG}_store
  export PBR_PETSC_OUT=$P/${TAG}_l${LVL}_pc_k${K}_r${R}.csv
  export PBR_SOLVER_OUT=$P/${TAG}_l${LVL}_sv_k${K}_r${R}.csv
  rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"
  local S=$(date +%s%3N)
  interFoam > log.r${R}k${K} 2>&1
  local E=$(date +%s%3N)
  local fatal=$(grep -c "FOAM FATAL" log.r${R}k${K})
  local iters=$(awk '/Solving for p_rgh/{match($0,/No Iterations [0-9]+/);
                      s+=substr($0,RSTART+14,RLENGTH-14)} END{print s+0}' log.r${R}k${K})
  local nrb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' $PBR_PETSC_OUT 2>/dev/null)
  echo "lvl=$LVL K=$K round=$R wall_ms=$((E-S)) iters=$iters nrebuild=$nrb fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg)"
}

echo "=== covscan 开始 $(date '+%F %T')  KS=[$KS] NROUND=$NROUND ==="
for LVL in 10 20; do
  D=$P/${TAG}_l${LVL}
  rm -rf "$D"; cp -r $P/damBreak_petsc "$D"
  cd "$D" || exit 1
  foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null
  foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null
  foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null
  export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
  for R in $(seq 1 $NROUND); do
    for K in $KS; do
      run_one $LVL "$D" $K $R
    done
  done
done
echo "=== covscan 结束 $(date '+%F %T') ==="
echo "COVSCAN_DONE"
