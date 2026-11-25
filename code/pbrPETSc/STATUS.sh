#!/bin/bash
# 一条命令看夜间实验进度与结果
cd /root/autodl-tmp/PBR
echo "════════════════════════════════════════════════════════════"
echo "  时间: $(date)"
echo "  主计划: $(pgrep -cf run_night_plan.sh) 个进程"
echo "  接力:   $(pgrep -cf run_after_night.sh) 个进程"
echo "  计算:   $(pgrep -cf interFoam) 个 interFoam"
echo "════════════════════════════════════════════════════════════"
echo "  计划日志:"
grep -E "PLAN START|finished| ALL DONE|接力开始|审计完成|接力全部结束" night_plan.out after_night.out 2>/dev/null
echo "════════════════════════════════════════════════════════════"
for f in x3_scan.out fl10_scan.out fl30_scan.out; do
  if [ -f "$f" ]; then
    echo ""
    echo "── $f : $(grep -c "^round=" "$f") 次运行 ──"
    grep "^round=" "$f"
  fi
done
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ★ 数据审计（行数=nBuildPC，ΣtPCSetup=tSetupAll）"
echo "════════════════════════════════════════════════════════════"
[ -f audit_night.txt ] && cat audit_night.txt || echo "  (审计尚未运行)"
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ★ 分析结果"
echo "════════════════════════════════════════════════════════════"
[ -f analyze_mesh_all.txt ] && cat analyze_mesh_all.txt || \
  { [ -f analyze_mesh_x3.txt ] && cat analyze_mesh_x3.txt || echo "  (分析尚未运行)"; }
