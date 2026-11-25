# 算例输入

本目录只含**输入**，不含任何时间步输出、后处理结果或日志。

| 目录 | 内容 | 大小 | 来源 |
|---|---|---|---|
| `openfoam/fx` `l15` `l20` | damBreak，基准网格 2268 单元，ILU(10/15/20) | 各 ~0.7 MB | OpenFOAM v2406 官方 `damBreak` 教程，有改动 |
| `openfoam/fine` `fl30` | damBreak，2 倍加密 9072 单元，ILU(20/30) | 各 ~1.9 MB | 同上 |
| `openfoam/x3` | damBreak，3 倍加密 20412 单元，ILU(20) | 4.1 MB | 同上 |
| `openfoam/sth` | Stefan 相变问题，ILU(5)，边界算例 | 0.4 MB | OpenFOAM v2406 官方 Stefan 教程，有改动 |
| `aspect/blankenbach` | Blankenbach case 2a 的 `.prm` + 初始温度场 + 插件构建脚本 | 56 KB | ASPECT 2.4.0 官方 benchmark，网格加密 4→5 |
| `aspect/tosi` | Tosi et al. (2015) Case 1/3/4/5 的 `.prm` | 16 KB | ASPECT 2.4.0 官方 benchmark，仅截短 End time |
| `moose/step6a` | darcy_thermo_mech step6a 耦合算例 + 材料数据表 | 12 KB | MOOSE 官方 tutorial，**未改动** |
| `elmer/fssa_perlin2d` | 冰川流 FSSA 回归测试（.sif + 网格 + 地形数据） | 236 KB | Elmer/Ice 官方测试，**未改动** |
| `lamem/rifting2d` | Rifting2D_MultigridSolver 参数文件 | 16 KB | LaMEM 官方算例，**未改动**（nstep_max 由脚本截短） |

每个 OpenFOAM 算例目录下的 `SOURCE.md` 逐条列出相对官方教程的全部改动。

## 重要：OpenFOAM 算例不是官方原设置

六个 damBreak 配置相对官方教程有以下改动，撰写或评审时须以 `SOURCE.md` 为准：

1. 压力方程求解器由 `PCG + DIC` 换为 `PBRPCG + PETScILU`（这是被研究的对象本身）。
2. 收敛判据统一为 `tolerance 1e-08`、`relTol 0`、`maxIter 20000`；官方为 `1e-07`、`relTol 0.05`。**统一是为了让 DIC 对照与 ILU(k) 用同一判据**，否则不可比。
3. `nLimiterIter` 由 5 改为 3。
4. `adjustTimeStep` 写作 `on`（语义同官方的 `yes`）。
5. `controlDict` 增加 `libs` 挂载策略与计时插件。
6. 删除官方的 `functions { #sinclude "sampling" }` 后处理块。
7. 网格在 fine/fl30/x3 上做 2×/3× 加密。

**`sth` 另有两处口径差异**（脚本已内置，不要手工改）：`endTime` 取 $20$（官方教程为 $50$，历史长批为 $100$；本文数据全部来自 20 那一批，统一截取前 $5866$ 步）；预热基数 $B_0 = 100$（与六个 damBreak 相同；统一的是参数值而非覆盖量，$B_0$ 按时间步计）；起跑从 $t = 1.36$ 开始、用 `setAlphaField` 生成初始相分布，不走 `blockMesh` + `setFields`。详见 `openfoam/sth/SOURCE.md`。

**`fvSolution.dicfrozen` 不参与本文的 DIC 对照**：六个 damBreak 目录里的这份文件是早期 DICFrozen 探测的遗留，论文的 DIC 对照由脚本现场改写为原生 `PCG + DIC`。见各配置的 `SOURCE.md`。

**Tosi 四个算例统一用 `Tosi_base.prm`（`End time = 0.0063`）**；`Tosi_base_Case4.prm` 的 $0.03$ 属探索性批次，不产生论文数字。见 `aspect/tosi/README.md`。

## 许可

- OpenFOAM 教程文件及其修改版本：**GPL-3.0**
- ASPECT benchmark 文件及其修改版本：**GPL-2.0-or-later**
- MOOSE tutorial 文件：**LGPL-2.1**

本目录**不重新声明**这些第三方文件的许可，随各自宿主代码适用。

**重要**：凡在本仓库内被修改过的第三方文件（如 OpenFOAM 的 `fvSolution`、`controlDict`，ASPECT 的 `case.prm`、`Tosi_base.prm`），其修改版本**继承原文件的许可**（GPL-3.0 / GPL-2.0-or-later），不因收录进本仓库而变为 BSD-3-Clause。项目的 BSD-3-Clause 仅适用于 `contrib/` 下独立创作的策略源码与补丁。

再分发前须确认各官方案例的许可条款（见 `docs/reproducibility_package_design_20261029.md` 第七节未决问题 B1）。
