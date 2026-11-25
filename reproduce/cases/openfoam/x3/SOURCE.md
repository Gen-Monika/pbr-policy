# 算例来源与改动：x3（OpenFOAM damBreak）

## 出处

基础算例为 OpenFOAM v2406 官方教程 `tutorials/multiphase/interFoam/laminar/damBreak/damBreak`。

## 相对官方教程的改动（必须如实告知）

本算例**不是**官方原设置，共有以下实质改动：

| 项 | 官方 | 本文 | 原因 |
|---|---|---|---|
| 网格 | 23 x 8（基准） | 69x24 = 3x refinement (20412 cells) | 见下 |

改动细节：

1. **网格**：69x24 = 3x refinement (20412 cells)
2. **求解器接口**：`p_rgh` / `p_rghFinal` 由 `PCG + DIC` 改为 `PBRPCG + PETScILU`，`levels = 20`（ILU(k) 填充级）。这是本文方法所研究的对象。
3. **容差统一**：`tolerance 1e-08`、`relTol 0`、`maxIter 20000`。官方为 `tolerance 1e-07`、`relTol 0.05`。**此处偏离官方是为了让 DIC 对照与 ILU(k) 使用完全相同的收敛判据**，否则两者的迭代数与墙钟不可比。
4. **`nLimiterIter`**：由 5 改为 3（MULES 通量限制器的迭代上限）。
5. **`adjustTimeStep`**：写作 `on`（官方 `yes`，语义相同）。
6. **`controlDict` 的 `libs`**：加入 `( libpbrSolverTimer.so libpbrPETSc.so )`，用于挂载策略与计时插件。
7. **删除 `functions { #sinclude "sampling" }`**：官方自带的后处理采样函数块，与本研究无关，为避免额外 IO 与干扰计时而移除。
8. **`0.orig` 增加湍流场文件**（`epsilon`、`k`、`nuTilda`、`nut`）：官方 damBreak 为层流，这四个文件在本算例中**未被使用**，保留仅因原目录如此。

## 未改动的部分

`blockMeshDict` 的块拓扑与 `simpleGrading`、`constant/g`、`constant/transportProperties` 的物理参数（仅空白差异）、`setFieldsDict`、`fvSchemes`、`endTime = 1`、`deltaT = 0.001`、`maxCo = 1`。

## 关于 `system/fvSolution.dicfrozen`（历史遗留，非本文 DIC 对照）

本目录另有一份 `system/fvSolution.dicfrozen`，内容为 `PCG + DICFrozen`（OpenFOAM 的冻结 DIC 预条件子，需 `libpbrDICFrozen.so`）。它是早期 DICFrozen 探测（2026-10 的负面结果实验）的遗留文件，**与论文的 DIC 对照无关**，运行时也不会被加载。

本文的 DIC 对照是**原生 `PCG + DIC`**，由运行脚本从 `system/fvSolution` 现场改写生成（`foamDictionary` 把 `p_rgh`/`p_rghFinal` 的 solver 改为 `PCG`、preconditioner 改为 `DIC`），日志中对应 `DICPCG:  Solving for p_rgh`。

同样，生产运行目录里还会出现一份 `system/fvSolution.pbr`，那是脚本在每个模式开始前对 `fvSolution` 的备份（内容与本目录的 `fvSolution` 相同），属运行中间态，不需要进包。

## 计时口径

论文中所有墙钟数字均为**同轮配对**（同一批、同一轮内四模式背靠背执行）的比值，不使用跨批绝对墙钟。

## 许可

OpenFOAM 官方教程文件按 GPL-3.0 分发。

**本目录中被修改过的文件（`system/fvSolution`、`system/controlDict`、`0.orig` 下的场文件等）是 GPL-3.0 作品的修改版本，因此仍按 GPL-3.0 分发**，不是 BSD-3-Clause。项目的 BSD-3-Clause 仅适用于本仓库独立创作的源码（`contrib/` 下的策略实现与补丁），不适用于本目录任何文件。

未修改的官方文件保持其原始许可。再分发时请保留 OpenFOAM 的版权声明。
