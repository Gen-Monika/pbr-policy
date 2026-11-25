#!/bin/bash
# ★★★ sth 覆盖补扫描（2026-10-12 修正版）
#
# ═══ 勘察结论（先把话说清楚）═══
# 现象：sth_pc_k1_r1.csv 等 12 个文件的 CSV 步数=5866，同名 log 步数=15642。
# 根因：stefan/ 目录被两个 endTime 批次复用，同名 log 被后来的长跑覆盖。
#
# 但这【不是数据错误】。实测核验：
#   · 短批(r4~r10, endTime=20) 与 长批(r1~r3, endTime=100) 的前 5866 步
#     迭代数序列【逐位完全相同】（6 个 K 全部 0 处差异）
#   · 第 5866 步的时间戳精确相同（20.00135295）
#   ⇒ 两条轨迹在前 5866 步是同一条；min(len,len) 截断是无损的。
#   （曾被一个假检查误导：nApplyCalls 是"步内计数器"0,1,2,3，
#     拿它去比 log 的求解次数必然全部不符。该检查已作废。）
#
# ═══ 本次要修的两处口径 ═══
#   (1) levels：历史 60 个 sth CSV 全部记录 levels=5，
#       上一版脚本误写 LVL=4 ⇒ 改回 5
#   (2) endTime：保持 20（与全部 A 阶段分析口径一致，T=5866）
#
# ═══ 覆盖缺口 ═══
#   已有 K ∈ {1,2,3,5,8,13}；补 K ∈ {20,30}
#   为让整批同质（避免与长批 log 混用），全部重跑，3 轮。
#
# ⚠️ 同时设 FREEZE_AT 与 FREEZE_K（只给 K 会静默退化为 K=1）
# ⚠️ Stefan 初始化顺序：先 cp -rf 0 1.36 再 setAlphaField（颠倒会报缺文件）
# ⚠️ 必须保留官方 1.36 目录（它是起跑点）；BASE=50 沿用历史口径
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH
export OMP_NUM_THREADS=1
export PBR_PETSC_KIND=ilu
export PBR_PETSC_BENCH=1
export PBR_PETSC_REPS=8

P=/root/autodl-tmp/PBR
NROUND=${NROUND:-3}
KS=${KS:-"20 30"}
LVL=5
BASE=50
ET=20
D=$P/cov2b_sth

rm -rf "$D"
cp -r "$P/stefan" "$D" || { echo "复制失败"; exit 1; }
cd "$D" || exit 1

# endTime 改回 20（源目录现在是 100，那是长批遗留）
foamDictionary system/controlDict -entry endTime -set $ET > /dev/null 2>&1
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

clean_times() {
  for d in */; do d=${d%/}
    case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
    if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      [ "$d" = "1.36" ] && continue      # 官方起跑点，必须留
      rm -rf -- "$d"
    fi
  done
}

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null 2>&1
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null 2>&1
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null 2>&1
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

echo "=== cov2b/sth 开始 $(date '+%F %T')  levels=$LVL BASE=$BASE endTime=$ET Ks=[$KS] rounds=$NROUND ==="

for R in $(seq 1 $NROUND); do
  for K in $KS; do
    clean_times
    rm -rf 1.36
    cp -rf 0 1.36
    setAlphaField > log.sf 2>&1

    unset PBR_PETSC_ONLINE
    export PBR_PETSC_LEVELS=$LVL
    export PBR_PETSC_FREEZE_AT=1
    export PBR_PETSC_FREEZE_BASE=$BASE
    export PBR_PETSC_FREEZE_K=$K
    export PBR_PETSC_STORE=$P/cov2b_store_sth
    export PBR_PETSC_OUT=$P/cov2b_sth_pc_k${K}_r${R}.csv
    export PBR_SOLVER_OUT=$P/cov2b_sth_sv_k${K}_r${R}.csv
    rm -f "$PBR_PETSC_OUT" "$PBR_SOLVER_OUT"

    S=$(date +%s%3N)
    timeout 1800 interCondensatingEvaporatingFoam > log.r${R}k${K} 2>&1
    E=$(date +%s%3N)
    fatal=$(grep -c "FOAM FATAL" log.r${R}k${K})
    nsteps=$(grep -c "^Time = " log.r${R}k${K})
    nuniq=$(awk -F, '{c[$1]=1} END{print length(c)}' "$PBR_PETSC_OUT" 2>/dev/null)
    nrb=$(awk -F, '$7>=0 && $9==0 {s[$1]=1} END{print length(s)}' "$PBR_PETSC_OUT" 2>/dev/null)
    lv=$(head -1 "$PBR_PETSC_OUT" 2>/dev/null | cut -d, -f4)
    ok="OK"; [ "$nuniq" != "$nsteps" ] && ok="★步数不匹配"
    echo "sth K=$K R=$R wall_ms=$((E-S)) nsteps=$nsteps csvuniq=$nuniq nrebuild=$nrb fatal=$fatal levels=$lv $ok"
  done
done
echo "=== cov2b/sth 结束 $(date '+%F %T') ==="
echo "COV2B_STH_DONE"
