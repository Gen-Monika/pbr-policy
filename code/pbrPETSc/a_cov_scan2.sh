#!/bin/bash
# ★★★ A-补扫描 2：把其余五个配置的年龄覆盖也推到 ~30
#
# 动机（见 a_final_merged.py 的结果）：
#   fx/l20 补到 K=30 后，在线的 regret 从 13.05% 降到 3.46%（fx）
#   ⇒ 此前的"在线差"是稀疏表的洞造成的假象。
#   要让七个配置可横向对比，必须补齐同样的覆盖。
#
# 各配置的缺口：
#   l15  (levels=15, l15/)     : 已有 k1-8   → 补 13 20 30
#   fine (levels=20, finerun/) : 已有 k1-8   → 补 13 20 30
#   x3   (levels=20, x3run/)   : 已有 k1-8   → 补 13 20 30
#   fl30 (levels=30, fl30run/) : 已有 k1,3,5  → 补 8 13 20 30
#   sth  (Stefan, stefan/)     : 已有 k1-13  → 补 20 30
#
# ⚠️ 同时设 FREEZE_AT 与 FREEZE_K（只给 K 会静默退化为 K=1）
# ⚠️ 不用 set -e；foamDictionary 后重导 LD_LIBRARY_PATH；setsid nohup
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

P=/root/autodl-tmp/PBR
TAG=${TAG:-cov2}
NROUND=${NROUND:-3}

# name:levels:basedir:csvprefix:Ks
SPECS="
l15:15:$P/l15:l15:13 20 30
fine:20:$P/finerun:fine:13 20 30
x3:20:$P/x3run:x3:13 20 30
fl30:30:$P/fl30run:fl30:8 13 20 30
sth:4:$P/stefan:sth:8 13 20 30
"

echo "=== $TAG 开始 $(date '+%F %T') ==="
echo "$SPECS" | while IFS=: read -r NAME LVL SRC PFX KS; do
  [ -z "$NAME" ] && continue
  D=$P/${TAG}_${NAME}
  rm -rf "$D"
  cp -r "$SRC" "$D" 2>/dev/null || { echo "!! $NAME 复制失败"; continue; }
  cd "$D" || continue

  # 清掉旧的时间目录
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing|0.*) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
  done

  # 确认求解器配置（复制来的可能已是 PBRPCG，但保险起见重设）
  foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null 2>&1
  foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null 2>&1
  foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null 2>&1
  export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

  echo "--- $NAME  levels=$LVL  src=$SRC  Ks=[$KS] ---"
  for R in $(seq 1 $NROUND); do
    for K in $KS; do
      for d in */; do d=${d%/}
        case "$d" in 0|0.orig|system|constant|postProcessing|0.*) continue;; esac
        if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
      done
      rm -rf 0 && cp -r 0.orig 0
      blockMesh > log.bm 2>&1
      # Stefan 需要 setAlphaField；其余 damBreak 用 setFields
      if [ "$NAME" = "sth" ]; then
        setAlphaField > log.sf 2>&1 || true
      else
        setFields > log.sf 2>&1
      fi

      unset PBR_PETSC_ONLINE
      export PBR_PETSC_LEVELS=$LVL
      export PBR_PETSC_FREEZE_AT=1
      export PBR_PETSC_FREEZE_BASE=100
      export PBR_PETSC_FREEZE_K=$K
      export PBR_PETSC_STORE=$P/${TAG}_store
      export PBR_PETSC_OUT=$P/${TAG}_${PFX}_pc_k${K}_r${R}.csv
      export PBR_SOLVER_OUT=$P/${TAG}_${PFX}_sv_k${K}_r${R}.csv
      rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"

      SOLVER=$( [ "$NAME" = "sth" ] && echo interCondensatingEvaporatingFoam || echo interFoam )
      S=$(date +%s%3N)
      $SOLVER > log.r${R}k${K} 2>&1
      E=$(date +%s%3N)
      fatal=$(grep -c "FOAM FATAL" log.r${R}k${K})
      nsteps=$(grep -c "^Time = " log.r${R}k${K})
      nrb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' "$PBR_PETSC_OUT" 2>/dev/null)
      echo "$NAME K=$K R=$R wall_ms=$((E-S)) nsteps=$nsteps nrebuild=$nrb fatal=$fatal"
    done
  done
  cd $P
done
echo "=== $TAG 结束 $(date '+%F %T') ==="
echo "${TAG}_DONE"
