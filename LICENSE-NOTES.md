# 许可与分发说明

本仓库适用 BSD 3-Clause（见 `LICENSE`）。但仓库内含若干**以补丁或独立模块形式**接入第三方求解器的代码，这些部分本身不是第三方软件的再分发，适用性说明如下。

## 本仓库不包含第三方代码

`code/` 下的 `aspect_pbr`、`moose_pbr`、`lamem_pbr`、`elmer_opm` 各目录只包含：

- 本项目新增的策略实现（头文件、Fortran 模块、patch 片段）
- 应用方法与验证说明

**不含** ASPECT、MOOSE、LaMEM、Elmer、OpenFOAM 的任何原始源码。使用前需自行获取这些软件并遵守其各自许可：

| 软件 | 许可 |
|---|---|
| ASPECT | GPL-2.0-or-later |
| MOOSE | LGPL-2.1 |
| LaMEM | 见其仓库 |
| Elmer | GPL-2.0 |
| OpenFOAM | GPL-3.0 |
| PETSc | BSD-2-Clause |

## 补丁的分发方式

补丁与宿主软件分离分发，因此 BSD-3 与本仓库不构成对 GPL 类宿主的许可冲突：本仓库发布的是独立创作的修改片段，不是宿主的衍生作品整体。用户在将其应用于 GPL 软件后，所产生的组合物适用该软件的许可。

## 数据与引用

- `data/` 与 `reproduce/expected/` 下的实测数据可随代码一并使用，引用时请注明本仓库与论文。
- 论文文稿与第三方文献不随本仓库分发；引用格式见根目录 `README.md`。
