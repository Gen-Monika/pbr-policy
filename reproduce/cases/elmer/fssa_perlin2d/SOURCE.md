# Elmer/Ice FSSA_perlin2d

## 出处

Elmer/Ice 官方回归测试 `elmerice/Tests/FSSA_perlin2d`。输入文件（`.sif`、`bedrock.dat`、`surf.dat`、`perlin.lua`、`mesh2D/`）**与官方逐字相同**，已用 `diff` 核对，未作修改。

该算例求解耦合 Glen 非牛顿流动律（$n=3$）与自由表面移动网格的二维冰川 Stokes 流动，20 个物理时间步，采用「先 Picard 后 Newton」混合非线性迭代，共约 270 次线性求解；线性求解器为官方配置的 GCR + ILU(1)，官方默认 `Linear System Precondition Recompute = 1`（每次求解都重建）。

## 用哪个 .sif

目录里有官方提供的两个 `.sif`，物理相同、离散不同：

| 文件 | 速度/压力单元 | 备注 |
|---|---|---|
| `stabilized.sif` | 等阶 `n:1`，压力由压力稳定化承担 | **本文使用这一个** |
| `Stokes_prognostic_nonlWeert.sif` | MINI 单元（`p:1 b:1`，气泡） | 未用于本文 |

两者都是官方回归测试，参考解的相对差约 $0.3\%$。论文中 Elmer 的表格与文字全部取自 `stabilized.sif`；`ELMERSOLVER_STARTINFO` 指向官方默认的 `Stokes_prognostic_nonlWeert.sif`，因此**不能**依赖它，必须显式给出文件名（`scripts/run_elmer.sh` 已如此）。

## 相对官方的改动（两处，均在运行时注入，不改本目录文件）

1. `Simulation` 段 `Max Output Level` 由 5 改为 8，使三个计时器写日志；
2. `Solver 2`（Stokes-Vec）段末尾追加判据开关 `Linear System Precondition Online = Logical True` 以及 `Linear System Timing`、`Linear System Residual Output`。

第 2 项是判据的接入点，官方算例没有。目录内保留官方原文，注入由 `../../scripts/run_elmer.sh` 完成，便于用 `diff` 核对官方原样。

## 论文中的用法

边界算例（$\rho \approx 3$--$4$，重建代价极低）：策略自动退化为几乎每次重建（$271$ 次求解中重建 $270$ 次），总成本仅比官方默认高 $0.2\%$。用于说明低构建代价区制下方法不会退化。

## 改动的部分在求解器，不在算例

判据以独立 Fortran 模块接入 Elmer 核心求解器 `IterSolve.F90`，并在 `IterativeMethods.F90` 中补齐 GCR 求解器的迭代步数回填字段。这两处属于 `contrib/elmer/`，不在此目录。关闭开关时与原版逐位一致。

## 运行

```bash
PBR_ROOT=/path/to/repo POLICY=online \
  ELMER_SOLVER=/path/to/ElmerSolver bash ../../scripts/run_elmer.sh
```

## 许可

Elmer 为 **GPL-2.0**（`LICENSE.md`）。本目录文件原样收录，保留其许可条款。
