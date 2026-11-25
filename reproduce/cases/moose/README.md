# MOOSE darcy_thermo_mech step6a

## 文件

- `step6a_coupled.i`：与 MOOSE 官方 `tutorials/darcy_thermo_mech/step06_coupled_darcy_heat_conduction/problems/` 下同名文件**逐字相同**（已 diff 核对）
- `step6a.py`：官方驱动脚本
- `data/*.csv`：官方材料数据表（水密度、比热、导热系数、黏度）

## 相对官方的改动

输入文件无改动。运行时仅通过命令行关闭与求解无关的 `exodus` 输出（`Outputs/exodus=false`）并加 `-log_view`。

## 注意

官方默认情况下 libMesh 会在求解之间重建 KSP 对象，使预条件子复用无法生效。为使对照成立，本研究的补丁版统一加 MOOSE 官方参数 `reuse_preconditioner=true` 与 `reuse_preconditioner_max_linear_its=1000000`，让 libMesh 保持同一 KSP 对象，重建与否只由判据钩子决定。该设置对对照组同样适用。

## 许可

来自 MOOSE 官方 tutorial，LGPL-2.1。
