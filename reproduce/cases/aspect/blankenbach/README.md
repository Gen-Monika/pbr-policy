# ASPECT Blankenbach case 2a

## 相对官方的改动

三处，均为显式追加或单行替换，便于用 `diff` 核对：

1. `Initial global refinement` 由 `4` 提高至 `5`（第 88 行，$13\,764$ 自由度）。
2. 文件末尾追加 `set End time = 0.1`（第 122 行），覆盖第 5 行的官方 `1.0`。这一条是**为控制调试与对照实验的墙钟规模而截短模拟时长**，不改变物理：`Ra`、黏度律、边界条件、初始温度场与时间推进参数全部保留官方值；截短后算例仍在同一物理区制内，含 $1626$ 个时间步。官方全长运行（`End time = 1.0`，$6638$ 步，约 $25$ 分钟）可作为可选延长实验，本文表格中的数字均取 $0.1$ 版本。
3. **从 `List of postprocessors` 中删去 `temperature ascii out`**（第 107 行）。原因见下节；删除它不影响任何论文数字。

## ★ 多进程运行必须删去 `temperature ascii out`

官方 benchmark 插件中的 `TemperatureAsciiOut` postprocessor（ASPECT 2.4.0 `benchmarks/blankenbach/plugin/code.cc`，`TemperatureAsciiOut<dim>::execute()`）**不支持 MPI 并行**：它从 `dof_handler.begin_active()` 遍历到 `end()` 取得所有单元（含 ghost 与人工单元），既不做 `cell->is_locally_owned()` 过滤，也不把结果归约到 rank 0，而是**每个 rank 各自用 `std::ofstream` 写同一个文件**。因此在 $n\ge 2$ 进程时它会在第一个时间步的 Postprocessing 阶段触发段错误。

实测（2026-11-02，ASPECT 2.4.0 + deal.II 9.3.2 + Open MPI 4.1.2）：

| 配置 | $n=1$ | $n=2$ | $n=4$ | $n=8$ |
|---|---|---|---|---|
| 官方未改 `case.prm`（含该项） | 正常跑完 | **段错误** | **段错误** | **段错误** |

这一点与本文的重建策略**无关**：用未打任何 PBR 补丁的官方 `build/aspect` 同样复现。逐项二分确认只有这一项会崩——`visualization`、`velocity statistics`、`temperature statistics`、`heat flux statistics`、`heating statistics`、`heat flux densities` 单独任一项都能在 $n=2$ 下跑完 $462$ 步。

因此：**做多进程复现时，请从 `case.prm` 的 `List of postprocessors` 中删去 `temperature ascii out`**，或改为在插件源码里补 `is_locally_owned()` 过滤并用 `Utilities::MPI::gather` 汇总后由 rank 0 写文件。后者是对 GPL-2.0+ 第三方插件的修改，需自行记录。本包默认已删去该项，故 $n=1$ 与 $n\ge2$ 均可直接运行。

删除后单进程的物理结果不受影响（该 postprocessor 只写一个文本文件，不参与求解）；它曾被官方 benchmark 用于导出温度剖面文本，本文未使用该输出。

其余（`Ra = 1e4`、温度相关指数黏度、初始温度场）均为 ASPECT 2.4.0 官方 `benchmarks/blankenbach/base_case2a.prm` 原值。注意 ASPECT 允许同一参数后被覆盖，`set End time = 0.1` 写在末尾才生效；若手工删去这一行，步数将由 $1626$ 变为 $6638$，`expected/aspect.csv` 的校验量随之不适用。

`initial_temperature_case2a.txt` 与官方文件 md5 相同（`53e430611aa981ef7302d0f1526473c1`）。

## 插件

`plugin/` 目录只有 `CMakeLists.txt`。所需的 `code.cc` 来自 ASPECT 官方 `benchmarks/blankenbach/plugin/`，**不随本包分发**（GPL-2.0+），请从官方仓库获取后与本 CMakeLists 一起编译为 `libblankenbach.so`。

## 运行

```bash
# 1. 编译插件（需已安装 ASPECT 2.4.0 且 deal.II 可被找到）
cd plugin && cmake . && make
# 2. 运行（PBR_LOG 给出逐求解轨迹 CSV；PBR_POLICY 不给则等价于官方默认）
PBR_POLICY=online PBR_BASE=100 PBR_LOG=$PWD/trace.csv aspect case.prm
```

`case.prm` 第 3 行 `set Additional shared libraries = ./plugin/libblankenbach.so` 已指向该位置。若 ASPECT 的 `cmake` 找不到 deal.II，需先设 `DEAL_II_DIR` 或用发行版里 deal.II 的包路径（本项目的构建机把 deal.II 解包在非标准前缀，运行前需把它的 `lib` 目录加入 `LD_LIBRARY_PATH`，否则报 `libtrilinos_ml.so.13.2: cannot open shared object file`）。

预期：$1626$ 个时间步、$1626$ 次 Stokes 求解，单进程约 $300$ s（Xeon 8352V，`OMP_NUM_THREADS=1`）。确定性校验量见 `../../../expected/aspect.csv`。

## 许可

`.prm` 与初始场文件来自 ASPECT 官方 benchmark，GPL-2.0+。
