#!/bin/bash
# LaMEM 长序列等价性检验（2026-10-29，计时实验已结束，不污染任何墙钟数据）
# 目的：把「关闭开关不改变数值路径」升级为「逐位一致」提供实测支撑。
#   同一官方算例 Rifting2D_MultigridSolver.dat，仅把 nstep_max 由 200 降到 NSTEPS，
#   与原版 LaMEM.orig 并排跑，比较全部输出文件 md5、SNES 残差序列、物理残差。
# 只写新目录（eq50_*），不覆盖 10-16/17 的 reg_* 与 r*_* 数据。
export PATH=/root/miniconda3/bin:$PATH OMP_NUM_THREADS=1
export HWLOC_COMPONENTS=-opencl,-gl,-cuda,-nvml
NSTEPS=${NSTEPS:-50}
L=$1; B=$2
SRC=/root/autodl-tmp/envs/lamem/src
O=$SRC/examples/BuiltInSetups/Rifting2D_MultigridSolver.dat
W=/root/autodl-tmp/PBR/lamem_cases/runs/$L
rm -rf "$W" && mkdir -p "$W" && cd "$W" || exit 1
sed "s/^\(\s*nstep_max\s*=\s*\)[0-9]*/\1$NSTEPS/" "$O" > case.dat
if [ "$B" = orig ]; then EXE=$SRC/bin/opt/LaMEM.orig; else EXE=$SRC/bin/opt/LaMEM; fi
# 补丁版显式清空 PBR_POLICY（默认即 off，此处显式化以免继承环境）
if [ "$B" = pbr ]; then unset PBR_POLICY; export PBR_POLICY=off; fi
export PBR_LOG=$W/pbr.csv
start=$(date +%s.%N)
$EXE -ParamFile case.dat -log_view > run.log 2>&1
rc=$?
python3 -c "import time;print('EXTWALL %.3f RC $rc'%(time.time()-$start))" >> run.log
echo "$L DONE rc=$rc nsteps=$NSTEPS bin=$B" >> /root/autodl-tmp/PBR/lamem_cases/eq_status
