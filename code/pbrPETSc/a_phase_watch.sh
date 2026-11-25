#!/bin/bash
# 等待相位扫描 driver 结束，然后自动跑验收与主结果。
# 用法：setsid nohup bash a_phase_watch.sh > /dev/null 2>&1 < /dev/null &
cd /root/autodl-tmp/PBR || exit 1
L=phs.log
PY=/root/miniconda3/bin/python

echo "watcher 启动 $(date '+%F %T')" > phs_watch.log

# 最多等 8 小时
for i in $(seq 1 2880); do
  if grep -q "PHASE_DRIVER_DONE" "$L" 2>/dev/null; then
    echo "检测到 PHASE_DRIVER_DONE $(date '+%F %T')" >> phs_watch.log
    break
  fi
  sleep 10
done

if ! grep -q "PHASE_DRIVER_DONE" "$L" 2>/dev/null; then
  echo "超时未完成 $(date '+%F %T')" >> phs_watch.log
  exit 1
fi

# 稍等，确保文件写完
sleep 5
echo "开始验收 $(date '+%F %T')" >> phs_watch.log
$PY a_phase_verify.py > phs_verify.log 2>&1
echo "验收结束 退出码=$? $(date '+%F %T')" >> phs_watch.log
echo "PHASE_VERIFY_DONE" >> phs_watch.log
