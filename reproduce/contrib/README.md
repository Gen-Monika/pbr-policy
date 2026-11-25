# 代码贡献（contrib）

本目录是论文方法的**全部实现**，按宿主求解器分目录。四套补丁/模块均为独立创作，按 BSD-3-Clause 分发；不包含任何宿主求解器的原始源码。

| 目录 | 形态 | 宿主 | 许可 |
|---|---|---|---|
| `openfoam-petsc/` | C++ 预条件子插件（非补丁） | OpenFOAM v2406 + PETSc | BSD-3 |
| `aspect/` | header-only 头文件 + 2 文件补丁 | ASPECT 2.4.0 | BSD-3 |
| `moose/` | 单文件补丁 | MOOSE | BSD-3 |
| `lamem/` | 2 文件补丁 | LaMEM | BSD-3 |
| `elmer/` | Fortran 模块 + 2 文件补丁 | Elmer/Ice | BSD-3 |

**先读 `MANIFEST.md`**：它记录了每个文件的 SHA-256、哪张论文表格由哪个版本产生，以及 ASPECT 头文件与补丁的强配套关系（错配会静默失效）。

## 快速开始

每套的 `README.md` 都给出：依赖、应用方法、最小可运行示例、环境变量、关闭开关后的等价性、已知失败情形。建议顺序：

1. 读 `MANIFEST.md` 第一、二节，确认文件配套。
2. 选一个宿主，按其 `README.md` 应用补丁并编译。
3. 用 `../cases/` 下对应算例，按 `../scripts/` 的运行脚本跑一次。
4. 对照 `../expected/` 的确定性计数校验。

## 一处容易踩的坑

`aspect/pbr_policy.h` 与 `aspect/aspect_pbr.diff` **必须配套**。头文件是"能编译但静默失效"的陷阱所在，详见 `MANIFEST.md` 第二节。请不要单独替换其中一个。

## 许可边界

补丁作用于 GPL 类宿主后，**组合物适用该宿主的许可**（ASPECT GPL-2.0-or-later、MOOSE LGPL-2.1、Elmer GPL-2.0、LaMEM MIT、OpenFOAM GPL-3.0）。用户需自行取得宿主软件并遵守其许可。本项目只发布独立创作的修改片段。
