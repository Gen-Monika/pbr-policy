# Elmer/Ice 接入

这是独立Fortran实现，不使用任何C++ pbr_policy.h。构建必须同时应用 `patches/elmer_IterSolve_full_pbr.diff` 与 `patches/elmer_IterativeMethods_full_pbr.diff`；后者回填GCR迭代计数。前者包含PBR_AlignAny首建谓词的集合对齐，避免潜在分支错配。建议Elmer 26.2及匹配MPI/Fortran工具链。

## 使用与回滚

从 `reproduce/` 目录按[主README](../../README.md)配置后，使用下述入口；不要手工再应用旧顶层diff。`build-sources.json` 是当前构建清单，`patches/stages/` 仅表示历史增量，不能叠加到完整补丁上。预检先检查全部目标、上下文和头文件，再写文件；重复执行当前版本不重复打补丁。

源码修改前保存 `source-backups` 与 `source_changes.json`。回滚按该清单恢复对应文件，或选择旧BIN/INSTALL；不reset整棵源码树、不删除旧输出。实际依赖、执行命令、已加载库和SHA256见build_report与execution JSON。版本为建议而非硬锁，未知源码上下文会明确停止。

```bash
bash scripts/build_elmer.sh NP=2
bash scripts/run_elmer.sh NP=8 PROFILE=c1b PBR_ALIGN=on
```

必须安装到独立INSTALL，验证实际加载其中libelmersolver.so，不能只看make成功或mtime。run显式选stabilized.sif的Stokes-Vec Solver 2，注入Linear System Precondition Online、Timing、Residual Output并修正STARTINFO；否则可能RC=0但无trace。Fortran原生没有PBR_POLICY/PBR_K/PBR_UNIT接口；包装POLICY由SIF转换，支持online/off/fixed K=1，拒绝不支持的组合。

`ElmerGrid 2 2 mesh2D -partition N 1 1` 三个方向值必须完整。缺第三轴时会打印错误却返回0、不生成分区目录，run另检目录。np8几何分区40文件已与C存档逐字节核对；不能擅换metis或无分区运行。

参考每rank271数据行、20490次迭代、184重建，八份pbr_trace.csv.rN。运行RC=0/ALL DONE不等于精度通过：参考误差6.178587E-06>1E-06，FAILED，**不推荐用该MPI配置复现参考精度**。分区方式对预条件子强度的影响未被单独分离。on/off在所测三轮各自稳定，不能归功于广播，不外推其他配置。

宿主与组合物的许可按该项目原声明执行；本项目自有部分见仓库LICENSE。
