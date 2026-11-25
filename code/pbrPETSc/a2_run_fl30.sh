#!/bin/bash
# ★★★ A2-B：判决性配置 fl30（damBreak fine + levels=30，r=147，7 个配置中效应量最大）
#
# 为什么换这里：
#   l20 上离线预测在线只赢固定周期 4.99 pp，而实机墙钟的逐轮离散度约 ±10%，
#   信噪比不足，无法判决。fl30 的离线差距是 30.47 pp，可分辨性高得多。
#
# 组：
#   K1   每步重建
#   K5   墙钟最优固定周期（criterion_accuracy: fl30 K5 是 K 扫描里的最优）
#   ONLs 在线（重建代价 = r，离线已验证）
#   ONLp 在线（重建代价 = 每步分解次数 × r）
#
# 用法：NROUND=3 TAG=a2B LEVELS=30 SRC=/root/autodl-tmp/PBR/fl30run bash a2_run_v2.sh
echo "本脚本只是包装：直接调用 a2_run_v2.sh"
echo "  NROUND=3 TAG=a2B LEVELS=30 SRC=/root/autodl-tmp/PBR/fl30run MODES='K1 K5 ONLs ONLp' bash a2_run_v2.sh"
