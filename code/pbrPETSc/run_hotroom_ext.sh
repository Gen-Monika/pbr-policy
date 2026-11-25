#!/bin/bash
# ★ 接力：等主扫描结束后，补跑 hotRoom 的 K=13, 20 两档
cd /root/autodl-tmp/PBR
echo "=== HOTROOM 扩档接力开始 $(date) ==="
for i in $(seq 1 240); do
  if ! pgrep -f run_hotroom.sh > /dev/null 2>&1; then
    echo "主扫描已结束（等待 $((i*30))s）"; break
  fi
  sleep 30
done
sleep 5
for K in 13 20; do
  for R in 1 2 3; do
    bash run_hotroom_single.sh $K $R > /dev/null 2>&1
  done
done
echo "=== HOTROOM 扩档完成 $(date) ==="
