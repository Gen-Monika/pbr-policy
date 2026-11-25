# MOOSE 接入

使用MOOSE自己的 `pbr_policy.h` 与 `patches/moose_NonlinearSystem_alignfix.diff`。头文件含PBR_COND和诊断列，不与ASPECT/LaMEM互换。建议使用与MOOSE源码配套的PETSc/libMesh/WASP工具链；本站为moose-env、Open MPI 5.0.10。

## 使用与回滚

从 `reproduce/` 目录按[主README](../../README.md)配置后，使用下述入口；不要手工再应用旧顶层diff。`build-sources.json` 是当前构建清单，`patches/stages/` 仅表示历史增量，不能叠加到完整补丁上。预检先检查全部目标、上下文和头文件，再写文件；重复执行当前版本不重复打补丁。

源码修改前保存 `source-backups` 与 `source_changes.json`。回滚按该清单恢复对应文件，或选择旧BIN/INSTALL；不reset整棵源码树、不删除旧输出。实际依赖、执行命令、已加载库和SHA256见build_report与execution JSON。版本为建议而非硬锁，未知源码上下文会明确停止。

```bash
bash scripts/build_moose.sh NP=8
bash scripts/run_moose.sh NP=8 PROFILE=c1b PBR_ALIGN=on
bash scripts/run_moose.sh NP=8 PROFILE=c1b PBR_ALIGN=off
```

build在Darcy step06应用目录构建，并在重编前备份framework/libmoose-opt.so*。run使用官方step6a输入，统一设置Executioner/reuse_preconditioner=true和reuse_preconditioner_max_linear_its=1000000，避免宿主自行重建KSP破坏复用。on/off都保留这些设置。

`PBR_ALIGNFIX=on && PBR_ALIGN=on` 才启用集体OR，属于门控关系。修复的是各rank本地KSP指针状态可能导致集合通信分支不匹配，不改est>avg公式。COND=index时从SNES取非线性迭代号；注册上下文必须是SNES。

当前np8参考每rank819数据行、2721迭代、152重建，八份pbr.csv.rN；串行历史expected是另一口径，不硬套。C步on/off各自三轮稳定不能归功于广播。`POLICY=off` 与 `PBR_ALIGN=off` 不同：前者关闭策略，后者保留策略但关闭对齐。

宿主与组合物的许可按该项目原声明执行；本项目自有部分见仓库LICENSE。
