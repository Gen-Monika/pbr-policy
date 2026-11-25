/**
 * ★ 隔离检验：Amul 在真实 CG 循环中的成本
 *
 * 背景：
 *   - 项目内孤立的 amulReplica 微基准给出 Amul ≈ 20 µs（2268 单元）
 *   - 但 solve() 层面计时的余项是 997/495/180 µs per iteration
 *   - 预条件子 apply 实测 112-130 µs（含两次 nCells 拷贝）
 *   ⇒ 余项远超 Amul 与 apply 之和 ⇒ 有未识别的开销
 *
 * 本文件的检验目标：在【与真实 CG 循环相同的访问模式】下测 Amul，
 * 即：反复对同一对向量做 Amul，但中间穿插预条件子 apply（模拟真实循环），
 * 看 Amul 是否变慢（cache/内存带宽竞争）。
 *
 * 说明：本文件是【分析文档】，实际测量通过
 *       run_amul_probe.sh 在 OpenFOAM 环境中完成（见该脚本）。
 */

#include <cstdio>

// 本文件不编译，仅作为分析记录。
// 真实测量见 run_amul_probe.sh 与 analyze_amul_probe.py

int main()
{
    printf(
        "Amul 的成本取决于：\n"
        "  1. 单元数（2268）与面数（4432）\n"
        "  2. 访存模式：diag/upper/lower + upperAddr/lowerAddr/losortAddr\n"
        "  3. cache 状态：孤立微基准反复读同一组数组 ⇒ 全在 L2/L3\n"
        "                 真实循环中被 CG 的其他向量与 PETSc 数据挤出 cache\n"
        "\n"
        "⇒ 孤立微基准（20 µs）是【上界性能】，真实循环中会更慢。\n"
        "⇒ 需要用 PBRPCG 的逐迭代计时来定位，而非继续做隔离微基准。\n");
    return 0;
}
