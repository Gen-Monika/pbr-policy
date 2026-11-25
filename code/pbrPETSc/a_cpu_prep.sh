#!/bin/bash
# 为 cpu_vs_wall 验证准备算例（复制 + blockMesh + setFields + 改求解器设置）
#
# ⚠️ 不能用 set -e：source OpenFOAM 的 bashrc 最后一条命令返回 1，
#    会让脚本在第一步就静默退出（已踩过）。
source /usr/lib/openfoam/openfoam2406/etc/bashrc
LDP=/root/miniconda3/lib:/root/OpenFOAM/root-v2406/platforms/linux64GccDPInt32Opt/lib
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

P=/root/autodl-tmp/PBR
TAG=${TAG:-cpuw}
SRC=${SRC:-$P/damBreak_petsc}
D=$P/${TAG}_case

rm -rf "$D"
cp -r "$SRC" "$D"
cd "$D"

foamDictionary system/fvSolution -entry solvers.p_rgh.solver      -set PBRPCG > /dev/null
foamDictionary system/fvSolution -entry solvers.p_rghFinal.solver -set PBRPCG > /dev/null
foamDictionary system/controlDict -entry libs -set "(libpbrSolverTimer.so libpbrPETSc.so)" > /dev/null
export LD_LIBRARY_PATH=$LDP:$FOAM_LIBBIN:$LD_LIBRARY_PATH

rm -rf 0 && cp -r 0.orig 0
blockMesh > log.bm 2>&1
setFields > log.sf 2>&1

# 清掉时间目录
for d in */; do d=${d%/}
  case "$d" in 0|0.orig|system|constant|postProcessing) continue;; esac
  if [[ "$d" =~ ^[0-9]+([.][0-9]+)?$ ]]; then rm -rf -- "$d"; fi
done

echo "已准备 $D"
grep -E "^endTime|^startTime" system/controlDict
grep -A1 "p_rgh" system/fvSolution | head -3
ls -d 0 0.orig system constant | tr '\n' ' '; echo
