#!/bin/bash
# 串行驱动：依次跑 l15 / fine / x3 / fl30 / sth 的补扫描
# 每个配置独立调用 a_cov2_one.sh，互不影响；失败也不会拖垮后面的。
# 用法：setsid nohup bash a_cov2_driver.sh > cov2b.log 2>&1 < /dev/null &
cd /root/autodl-tmp/PBR || exit 1
echo "=== driver 开始 $(date '+%F %T') ==="
for N in ${NAMES:-l15 fine x3 fl30 sth}; do
  echo ""; echo "########## $N ##########"
  NAME=$N NROUND=${NROUND:-3} TAG=${TAG:-cov2} bash a_cov2_one.sh
  echo "########## $N 退出码=$? ##########"
done
echo "=== driver 结束 $(date '+%F %T') ==="
echo "COV2_DRIVER_DONE"
