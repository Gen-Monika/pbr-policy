#!/bin/bash
# ★★★ A-补扫描 2（2026-10-12 第三版）
#
# ═══ 本版修的两个错 ═══
# (1) sth 的 LEVELS 写成了 4。实测历史 60 个 sth CSV 记录的全是 levels=5。
#     若按 4 跑，同一配置下 r 会在两批之间跳变，而 r 是判据的核心量。
#     → 改回 5。
# (2) sth 的 SRC 目录 stefan/ 里 controlDict 的 endTime 现在是 100（长批遗留），
#     而全部 A 阶段分析的口径是 endTime=20 / T=5866。
#     → 显式设 endTime=20，并在每次运行前核对。
#
# ═══ 其余配置(逐一核对过) ═══
#   l15  LVL=15 ✓ (历史 levels=15)   fine LVL=20 ✓ (历史 levels=20)
#   x3   LVL=20 ✓ (历史 levels=20)   fl30 LVL=30 ✓ (历史 levels=30)
#   全部 BASE=100 ✓
#
# ⚠️ 同时设 FREEZE_AT 与 FREEZE_K（只给 K 会静默退化为 K=1）
# ⚠️ Stefan 初始化顺序：先 cp -rf 0 1.36 再 setAlphaField（颠倒会报缺文件）
# ⚠️ 必须保留官方 1.36 目录；sth 的 BASE=50 沿用历史口径
# ⚠️ 不用 set -e；foamDictionary 后重导 LD_LIBRARY_PATH；setsid nohup
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

P=/root/autodl-tmp/PBR
NAME=${NAME:?必须给 NAME}
NROUND=${NROUND:-3}
TAG=${TAG:-cov2}

case "$NAME" in
  l15)  LVL=15 SRC=$P/l15      PFX=l15  KS="13 20 30"    SOLVER=interFoam ;;
  fine) LVL=20 SRC=$P/finerun  PFX=fine KS="13 20 30"    SOLVER=interFoam ;;
  x3)   LVL=20 SRC=$P/x3run    PFX=x3   KS="13 20 30"    SOLVER=interFoam ;;
  fl30) LVL=30 SRC=$P/fl30run  PFX=fl30 KS="8 13 20 30"  SOLVER=interFoam ;;
  sth)  LVL=5  SRC=$P/stefan   PFX=sth  KS="20 30"       SOLVER=interCondensatingEvaporatingFoam ;;
  *) echo "未知 NAME=$NAME"; exit 1 ;;
esac

D=$P/${TAG}_${NAME}
rm -rf "$D"
cp -r "$SRC" "$D" 2>/dev/null || { echo "!! 复制 $SRC 失败"; exit 1; }
cd "$D" || exit 1

if [ "$NAME" = "sth" ]; then
  BASE=50; ET=20
  foamDictionary system/controlDict -entry endTime -set $ET > /dev/null 2>&1
  export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
else
  BASE=100; ET=$(grep -E "^endTime" system/controlDict | tr -dc '0-9.')
fi

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      [ "$NAME" = "sth" ] && [ "$d" = "1.36" ] && continue
      rm -rf -- "$d"
    fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null 2>&1
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null 2>&1
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null 2>&1
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

echo "=== $TAG/$NAME 开始 $(date '+%F %T')  levels=$LVL  BASE=$BASE  endTime=$ET  Ks=[$KS]  solver=$SOLVER ==="
echo "    src=$SRC  workdir=$D"

for R in $(seq 1 $NROUND); do
  for K in $KS; do
    clean_times

    if [ "$NAME" = "sth" ]; then
      rm -rf 1.36
      cp -rf 0 1.36
      setAlphaField > log.sf 2>&1
    else
      rm -rf 0 && cp -r 0.orig 0
      blockMesh > log.bm 2>&1
      setFields > log.sf 2>&1
    fi

    unset PBR_PETSC_ONLINE
    export PBR_PETSC_LEVELS=$LVL
    export PBR_PETSC_FREEZE_AT=1
    export PBR_PETSC_FREEZE_BASE=$BASE
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_STORE=$P/${TAG}_store_${NAME}
    export PBR_PETSC_OUT=$P/${TAG}_${PFX}_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=$P/${TAG}_${PFX}_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"

    S=$(date +%s%3N)
    timeout 3600 $SOLVER > log.r${R}k${K} 2>&1
    E=$(date +%s%3N)
    fatal=$(grep -c "FOAM FATAL" log.r${R}k${K})
    nsteps=$(grep -c "^Time = " log.r${R}k${K})
    nuniq=$(awk -F, '{c[$1]=1} END{print length(c)}' "$PBR_PETSC_OUT" 2>/dev/null)
    nrb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' "$PBR_PETSC_OUT" 2>/dev/null)
    lv=$(head -1 "$PBR_PETSC_OUT" 2>/dev/null | cut -d, -f4)
    ok="OK"; [ "$nuniq" != "$nsteps" ] && ok="★步数不匹配"
    [ "$lv" != "$LVL" ] && ok="$ok ★levels=$lv≠$LVL"
    echo "$NAME K=$K R=$R wall_ms=$((E-S)) nsteps=$nsteps csvuniq=$nuniq nrebuild=$nrb fatal=$fatal levels=$lv load=$(cut -d' ' -f1 /proc/loadavg) $ok"
  done
done
echo "=== $TAG/$NAME 结束 $(date '+%F %T') ==="
echo "${TAG}_${NAME}_DONE"
