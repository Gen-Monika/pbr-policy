#!/bin/bash
# 串行驱动相位扫描（A=6，7 次/配置）。每配置独立，失败不影响后续。
# 用法：setsid nohup bash a_phase_driver.sh > phs.log 2>&1 < /dev/null &
cd /root/autodl-tmp/PBR || exit 1
echo "=== 相位扫描 driver 开始 $(date '+%F %T') ==="
for N in ${NAMES:-l20 l15 fx fine fl30 x3 sth}; do
  echo ""; echo "########## $N ##########"
  NAME=$N A=${A:-6} R=${R:-1} TAG=${TAG:-phs} bash a_phase_scan.sh
  echo "########## $N 退出码=$? ##########"
done
echo "=== driver 结束 $(date '+%F %T') ==="
echo "PHASE_DRIVER_DONE"
