# 算例来源与改动：sth（Stefan 相变问题）

## 出处

OpenFOAM v2406 官方 Stefan 相变教程（\`multiphase/phaseChange\` 类）。

## 相对官方的改动

1. **求解器接口**：\`p_rgh\` 改为 \`PBRPCG + PETScILU\`，\`levels = 5\`。
2. **容差统一**：与六个 damBreak 配置相同（\`tolerance 1e-08\`、\`relTol 0\`）。
3. **\`libs\`**：挂载策略与计时插件。
4. 辅助动量方程 \`Ux\`/\`Uy\` 保留官方的 50 次迭代上限（论文 \S8 记录了该上限的触顶次数）。

## 模拟时长：\`endTime = 20\`（非官方 50，非历史长批的 100）

官方 OpenFOAM v2406 的 \`StefanProblem\` 教程（\`tutorials/verificationAndValidation/multiphase/StefanProblem/setups.orig/interCondensatingEvaporatingFoam\`）为 \`startTime = 1.36\`、\`endTime = 50\`。**本文全部 sth 数据取自 \`endTime = 20\` 的运行**，并且各策略统一截取到共同的前 5866 个物理步（$t \approx 1.36 \to 20$）以便同窗口比较，论文表中的步数 $5866$ 即由此而来。

早期曾有一批 \`endTime = 100\` 的长运行（15642 步，目录中保留到 \`96.36\` 的时间输出）。该批**不产生本文任何数字**，但它把源目录的 \`controlDict\` 改成了 100 并留在那里；本包的 \`controlDict\` 一度照抄了这份混合态。2026-10-30 的覆盖检查（\`docs/reproduce_coverage_20261030.md\`）发现后已改回 20。

## 起跑流程（与 damBreak 不同）

sth 不从 $t=0$ 起跑，而是从 $t = 1.36$ 重开，且初始相分布由 \`setAlphaField\` 生成而非 \`setFields\`：

```bash
cp -rf 0 1.36          # 0.orig 的均匀初场复制为 1.36 起始目录
setAlphaField          # 按 system/setAlphaFieldDict 写入 alpha.liquid 的界面位置
interCondensatingEvaporatingFoam
```

本目录已随包提供 \`constant/polyMesh/\`（800 单元网格），**不需要跑 \`blockMesh\`**；也没有 \`setFieldsDict\`——damBreak 那套 \`blockMesh\` + \`setFields\` 流程套不到这个算例上。\`scripts/run_openfoam.sh\` 已按上述流程增加 \`sth\` 分支。

## 与 damBreak 的关键区别

- 每步 **4 次**压力求解（$s=4$），damBreak 为 3 次。
- 重建代价极低（$\rho \approx 17$），故在论文中作为**边界算例**，不属于 damBreak 六配置的墙钟区间。
- 老化曲线在 $a \approx 6$ 后饱和，严格离散凸性通过率为 0。

## 注意

\`0.orig\` 含相变初始场，属输入而非输出。1.1 GB 的原始目录中绝大部分是时间步输出，已剔除。

## 许可

OpenFOAM 官方教程文件 GPL-3.0。**本目录的修改版本（`system/fvSolution`、`system/controlDict` 等）同为 GPL-3.0**，非 BSD-3-Clause；BSD-3-Clause 仅适用于本仓库独立创作的策略源码。
