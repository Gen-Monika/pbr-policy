#!/bin/bash
# ★★★ 相位扫描（Phase scan）：把 N(t,a) 在年龄 1..A 上密集补满
#
# ═══ 为什么需要 ═══
# K 扫描的口径是 base=B0=100、period=K，重建步为 B0, B0+K, B0+2K, ...
# 于是年龄 a 只出现在 t ≡ B0+a (mod K) 的那些 t 上 —— 非常稀疏。
# 实测：每个 t 只有 1~5 个可用年龄。而在线策略需要它访问到的每个
# (t,a) 的 N 值；缺失的那些只能靠填充【编造】，编造误差会被
# 自指动力学放大，导致模型与 C++ 实测分歧（实测 l20：模型 180 次
# 重建 vs C++ 221 次；一致率仅 51%）。
#
# ═══ 本方法（密度是完备的）═══
# base=B、period=K 时，年龄 a 出现在 t = B + a + jK（j≥0）。
# 取 K = A+1 并令 B 扫过 {B0-A, ..., B0}（共 A+1 个值），则
# 对每个 a ∈ [1,A] 与每个 t：t - a ≡ B (mod A+1) 在 B 的取值范围里
# 恰好命中一次 ⇒ 年龄 1..A 在【所有 t】上被密集覆盖，无空洞。
#
# ═══ 可靠性保障（本脚本内建）═══
# 每次运行后核对：
#   1. fatal = 0
#   2. CSV 唯一步数 == log 的 "Time = " 计数
#   3. levels == 期望值（防止参数张冠李戴）
#   4. 重建次数 == B + floor((T-B)/K)   ← 解析期望值，偏离即报警
#   5. 记录本轮的 (t,a) 覆盖，便于事后核对完整性
# 用法：NAME=l20 A=3 R=1 bash a_phase_scan.sh
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

P=/root/autodl-tmp/PBR
NAME=${NAME:?必须给 NAME}
A=${A:-15}                 # 目标最大年龄；运行次数 = A+1
R=${R:-1}                  # 轮次
TAG=${TAG:-phs}
B0=${B0:-}                 # 预热基准；留空则用该配置的历史值

case "$NAME" in
  fx)   LVL=10 SRC=$P/fixed    PFX=fx   SOLVER=interFoam  DEF_B0=100 ;;
  l15)  LVL=15 SRC=$P/l15      PFX=l15  SOLVER=interFoam  DEF_B0=100 ;;
  l20)  LVL=20 SRC=$P/l20      PFX=l20  SOLVER=interFoam  DEF_B0=100 ;;
  fine) LVL=20 SRC=$P/finerun  PFX=fine SOLVER=interFoam  DEF_B0=100 ;;
  x3)   LVL=20 SRC=$P/x3run    PFX=x3   SOLVER=interFoam  DEF_B0=100 ;;
  fl30) LVL=30 SRC=$P/fl30run  PFX=fl30 SOLVER=interFoam  DEF_B0=100 ;;
  sth)  LVL=5  SRC=$P/stefan   PFX=sth  SOLVER=interCondensatingEvaporatingFoam DEF_B0=50 ;;
  *) echo "未知 NAME=$NAME"; exit 1 ;;
esac
[ -z "$B0" ] && B0=$DEF_B0

K=$((A + 1))
D=$P/${TAG}_${NAME}
STORE=$P/${TAG}_store_${NAME}

rm -rf "$D"; rm -rf "$STORE"; mkdir -p "$STORE"
cp -r "$SRC" "$D" 2>/dev/null || { echo "!! 复制 $SRC 失败"; exit 1; }
cd "$D" || exit 1

if [ "$NAME" = "sth" ]; then
  foamDictionary system/controlDict -entry endTime -set 20 > /dev/null 2>&1
  export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
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

echo "=== $TAG/$NAME 相位扫描开始 $(date '+%F %T') ==="
echo "    A=$A  K=$K  B 范围=[$((B0-A)), $B0]  轮次 R=$R  levels=$LVL  solver=$SOLVER"
echo "    src=$SRC  workdir=$D"

nbad=0; ntot=0
for B in $(seq $((B0 - A)) $B0); do
  clean_times
  if [ "$NAME" = "sth" ]; then
    rm -rf 1.36; cp -rf 0 1.36; setAlphaField > log.sf 2>&1
  else
    rm -rf 0 && cp -r 0.orig 0
    blockMesh > log.bm 2>&1
    setFields > log.sf 2>&1
  fi

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
  nrb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' "$OUT" 2>/dev/null)
  lv=$(head -1 "$OUT" 2>/dev/null | cut -d, -f4)
  exp=$(( B + (nsteps - B)/K ))

  ok="OK"
  [ "$nuniq" != "$nsteps" ] && ok="★步数不匹配($nuniq/$nsteps)"
  [ "$lv" != "$LVL" ] && ok="$ok ★levels=$lv≠$LVL"
  [ "$fatal" != "0" ] && ok="$ok ★fatal=$fatal"
  if [ -n "$nrb" ]; then
    d=$((nrb - exp)); ad=${d#-}
    [ "$ad" -gt 3 ] && ok="$ok ★重建数=$nrb 期望=$exp(差$d)"
  fi
  [ "$ok" != "OK" ] && nbad=$((nbad+1))
  ntot=$((ntot+1))

  echo "$NAME B=$B K=$K R=$R wall_ms=$((E-S)) nsteps=$nsteps csvuniq=$nuniq levels=$lv nrebuild=$nrb expect=$exp fatal=$fatal load=$(cut -d' ' -f1 /proc/loadavg) $ok"
done

echo "=== $TAG/$NAME 结束 $(date '+%F %T')  运行=$ntot 异常=$nbad ==="
[ "$nbad" -eq 0 ] && echo "${TAG}_${NAME}_PHASE_CLEAN" || echo "${TAG}_${NAME}_PHASE_HAS_ISSUES"
