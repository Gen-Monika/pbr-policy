#!/bin/bash
# 压噪声补测（2026-10-29）：三小配置 fx/l15/l20 严格顺序执行、8 轮、四模式轮换
#
# 动机：wallclock_full 批中 fx/l15/l20 的压力节省六轮极差 10-29 pp，
#       而 fine/fl30/x3 仅 1.3-2.1 pp。已定位噪声在单次分解耗时
#       （l15 K1 逐轮 9.74-11.76 ms，±10%），来自多作业并发的内存带宽争用。
#       故本批改为完全串行（同时只有 1 个作业），四模式仍同轮交错配对。
#
# 只写新 TAG（ws<cfg>r<轮>），不触碰 wd*/wp*/wt*/w*
P=/root/autodl-tmp/PBR
STAMP=$(date +%Y%m%dT%H%M%S)
BASE_LOG=$P/wallclock_small_$STAMP
echo "STAMP=$STAMP" > $P/wallclock_small_latest.txt
echo "BASE_LOG=$BASE_LOG" >> $P/wallclock_small_latest.txt

for CFG in fx l15 l20; do
  case $CFG in
    fx)  SRC=$P/fixed; L=10 ;;
    l15) SRC=$P/l15;   L=15 ;;
    l20) SRC=$P/l20;   L=20 ;;
  esac
  for R in 1 2 3 4 5 6 7 8; do
    case $(( (R-1) % 4 )) in
      0) ORD="K1 K3 ONLp DIC"  ;;
      1) ORD="K3 DIC K1 ONLp"  ;;
      2) ORD="ONLp K1 DIC K3"  ;;
      3) ORD="DIC ONLp K3 K1"  ;;
    esac
    echo "### $CFG round $R order=$ORD start $(date '+%F %T')" >> ${BASE_LOG}_${CFG}.log
    TAG=ws${CFG}r${R} SRC=$SRC LEVELS=$L NROUND=1 MODES="$ORD" \
      bash $P/a_wall.sh >> ${BASE_LOG}_${CFG}.log 2>&1
  done
  echo ${CFG}_DONE >> ${BASE_LOG}_status
done
echo ALL_DONE >> ${BASE_LOG}_status
