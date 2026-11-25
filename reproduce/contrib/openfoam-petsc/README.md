# OpenFOAM / PETSc 预条件子插件

本目录是**预条件子的实现本体**，不是给官方代码打的补丁。OpenFOAM 通过 `controlDict` 的 `libs` 项加载编译出的 `.so`，由 `fvSolution` 指定使用它。

## 文件

| 文件 | 作用 |
|---|---|
| `PETScPreconditioner.C` / `.H` | ILU($k$) 预条件子 + 在线重建判据（论文主实现） |
| `Make/files`、`Make/options` | wmake 构建描述 |
| `pbrDICFrozen/` | 对照用：官方 DIC 但可冻结/复用 |
| `pbrGAMG/` | 对照用：GAMG 预条件子 |
| `pbrSolverTimer/` | `PBRPCG` 求解器与求解计时器（`libpbrSolverTimer.so`） |

## 依赖

OpenFOAM v2406（本仓库用 v2406；`pbrSolverTimer` 依赖其 `PCG` 求解器基类）、PETSc（实测 3.18+）、GCC、MPI。

## 构建

**先设 `PETSC_DIR`。** `Make/options` 会依次尝试：`PETSC_DIR` 环境变量 → `pkg-config --variable=prefix PETSc` → `/usr/local`。若两者都没探到，会静默用 `/usr/local`，之后编译报 `petsc.h: No such file`。

```bash
# 0. 确认 PETSc 位置（scripts/verify_environment.sh 会打印探测结果）
export PETSC_DIR=/path/to/petsc     # 例如 /opt/petsc 或 $HOME/petsc

# 1. 设置 OpenFOAM 环境
source /path/to/openfoam2406/etc/bashrc

# 2. 策略插件（产出 libpbrPETSc.so 到 $FOAM_USER_LIBBIN）
cd <本目录>
wmake

# 3. 计时与求解器插件（产出 libpbrSolverTimer.so，**必需**：
#    没有它 fvSolution 里的 solver PBRPCG 无法解析）
cd pbrSolverTimer && wmake

# 4. 对照用（可选，仅复现 DIC/GAMG 对照时需要）
cd ../pbrDICFrozen && wmake
cd ../pbrGAMG && wmake
```

编译产物落在 `$FOAM_USER_LIBBIN`（通常是 `$HOME/OpenFOAM/<user>-<ver>/platforms/.../lib`）。运行时该目录必须在 `LD_LIBRARY_PATH` 中——OpenFOAM 的 `etc/bashrc` 已经包含它。

**实测坑**：`libpbrSolverTimer.so` 容易被漏掉。只编译策略插件时运行会报
`Unknown solver type PBRPCG`，而错误信息不提示缺哪个库。

## 最小可运行示例

在任一 OpenFOAM 算例中：

```
# system/controlDict
libs  ( libpbrSolverTimer.so libpbrPETSc.so );

# system/fvSolution
p_rgh
{
    solver          PBRPCG;
    preconditioner  PETScILU;
    tolerance       1e-08;
    relTol          0;
    maxIter         20000;
}
```

环境变量：

```bash
export PBR_PETSC_KIND=ilu PBR_PETSC_LEVELS=20   # ILU(20)
export PBR_PETSC_BENCH=1                        # 打开计时（在线策略需要）
unset  PBR_PETSC_ONLINE PBR_PETSC_FREEZE_AT PBR_PETSC_FREEZE_K
```

不设 `PBR_PETSC_ONLINE` 与 `PBR_PETSC_FREEZE_*` 时，每步重建，等价于论文的 $K=1$ 基线。

## 环境变量一览

| 变量 | 含义 |
|---|---|
| `PBR_PETSC_KIND` | 预条件子类型，`ilu` |
| `PBR_PETSC_LEVELS` | ILU 填充级 $k$ |
| `PBR_PETSC_BENCH` | `1` 打开隔离重复计时（在线策略必须） |
| `PBR_PETSC_REPS` | 隔离计时重复次数，默认 50 |
| `PBR_PETSC_ONLINE` | `1` 启用在线策略 |
| `PBR_PETSC_ONLINE_BASE` | 强制预热步数，默认 100 |
| `PBR_PETSC_ONLINE_RCOST` | `step`（论文口径，按步内 $s$ 次分解计）或 `solve` |
| `PBR_PETSC_FREEZE_K` | 固定周期 $K$（对照） |
| `PBR_PETSC_FREEZE_AT`、`PBR_PETSC_FREEZE_BASE` | 单点冻结（对照） |
| `PBR_PETSC_OUT` | 逐求解 CSV 输出路径 |
| `PBR_PETSC_STORE` | 快照存放目录 |

## 关闭开关后的等价性

**本插件没有"原版二进制"可以对照**——它本身就是预条件子，官方 OpenFOAM 不含此实现。可核验的是：不设 `PBR_PETSC_ONLINE` 与 `PBR_PETSC_FREEZE_*` 时，`PCDataSetup()` 走 `else` 分支、每次求解都调用 `buildPC()`，行为即论文的 $K=1$ 每步重建基线。论文以此基线（而非"官方默认"）作为参照，DIC 对照则以官方默认预条件子形式独立运行。

## 已知失败情形

- 本实现依赖 PETSc 的 `Mat` 与 OpenFOAM 的 `lduMatrix` 之间的一次性转换（`buildPETScMatrix`），每次重建都需重建该矩阵；网格非常大时转换开销不可忽略，论文的 `tAssemble` 列记录了这部分。
- 在线策略依赖实时分解计时，单次分解耗时在 10–16 ms 量级的小算例上（2268 单元）受宿主负载影响显著，压力模块节省的置信半宽达 ±2.4–6.2 个百分点（论文 \S8 已注明）。

## 许可

BSD-3-Clause。不使用 OpenFOAM 的派生源码，通过公开的 `lduMatrix` / `preconditioner` 接口接入。
