# ASPECT Tosi et al. (2015) 四算例

## 文件

| 文件 | 说明 |
|---|---|
| `Tosi_base.prm` | 公共基础设置，`End time = 0.0063`（**论文全部四个算例都用这一份**） |
| `Tosi_base_Case4.prm` | 同上，但 `End time = 0.03`（探索性批次用的余量版本，**不产生论文数字**） |
| `Tosi_Case{1,3,4,5}.prm` | 各算例的黏度/塑性参数，`ASPECT 2.4.0` 官方值 |

用法：`aspect Tosi_Case4.prm`，四个算例**都不需要**替换 `Tosi_base.prm`。

## 关于 `Tosi_base_Case4.prm`（易误用）

产生论文数字的生产运行（`stepB/phase_index_20261017_codex/full/C{1,3,4,5}/r*_old`）**四个算例统一使用 `End time = 0.0063`**，Case 4 亦然；C4 的生产轨迹为 1650 步，日志以 `Termination requested by criterion: end time` 结束。

`Tosi_base_Case4.prm` 的 $0.03$ 来自 ASPECT 侧的探索性批次（`aspect_runs/tosi/C4_V*`、`C4_S*`），那里的时间步更小，需要更长窗口才能积累足够多的求解次数。它**不产生本文任何数字**。

`scripts/run_aspect.sh` 在 `CASE=tosi4` 时会把它复制成 `Tosi_base.prm`。这样跑出来的统计窗口内确定性计数与论文一致（因为论文统一截取至 $t \le 0.0063$），只是要多跑约 5 倍时长。若只想核对表格数字，把该复制步骤去掉、直接用 `Tosi_base.prm` 更快。

## 相对官方的改动

- 仅截短 `End time`（官方为 `1`，约需两万步）。网格、物理参数、非线性求解格式均为官方值。
- **论文的统计窗口统一截取至 $t \le 0.0063$**，因此 Case 4 若用 0.03 那份 base 只是给出足够余量，实际参与统计的仍是前 0.0063 区间。各算例在该窗口内包含 461–1640 次 Stokes 求解。

## 插件

官方 benchmark 自带 `tosi.cc`，需按 `benchmarks/tosi_et_al_2015_gcubed/CMakeLists.txt` 编译为 `libtosi_benchmark.so`。本目录不重分发该源码（GPL-2.0+），请从 ASPECT 官方仓库获取。

## 许可

`.prm` 文件来自 ASPECT 官方 benchmark，GPL-2.0+。
