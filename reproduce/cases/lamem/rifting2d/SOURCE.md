# LaMEM Rifting2D_MultigridSolver

## 出处

LaMEM 官方自带算例 `examples/BuiltInSetups/Rifting2D_MultigridSolver.dat`（$256 \times 128$ 网格，耦合 Galerkin 几何多重网格 + 粗层 MUMPS LU）。**文件内容与官方逐字相同，未作任何修改**。

## 论文中的用法

该算例在论文 \S\ref{sec:scope-criterion} 中作为**负面算例**：跨物理时间步边界复用多重网格层次会在第 $9$ 步（永不重建、$K=10$）或第 $33$--$37$ 步（$K=2,3,5$ 与在线策略）触发 FGMRES 的 $50$ 次迭代上限。它不是正面性能证据。

## 运行时的参数截短

官方 `nstep_max = 200`（`time_end = 100`）。论文运行按需把它调低以缩短运行：等价性验证用 `5 / 12 / 50`，性能对比用完整设定。这**只改一行**，由运行脚本用 `sed` 完成，本目录保留官方原值。

复现等价性验证：

```bash
NSTEPS=50 bash scripts/run_lamem.sh eq50_pbr   # 补丁版, PBR_POLICY=off
NSTEPS=50 bash scripts/run_lamem.sh eq50_orig  # 原版二进制
```

两者输出应交逐字节一致（实测 75 个输出文件 md5 全同，SNES 686 条、KSP 4255 条残差序列全同）。

## 关闭开关的等价性

已实测：`PBR_POLICY` 未设（默认 `off`）时，补丁版与官方原版逐位一致；`K=1`（每次重建）时同样逐位一致。详见 `docs/lamem_pbr_equivalence_20261029.md`。

## 许可

LaMEM 为 **MIT** 许可（`LICENSE`，Copyright 2011–2026 JGU Mainz, Boris Kaus, Anton Popov）。本文件原样收录，保留其许可条款。
