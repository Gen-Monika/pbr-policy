# ASPECT 接入

当前交付是ASPECT专用 `pbr_policy.h` 和三份完整接入补丁（assembly/core/solver），见[MANIFEST](../MANIFEST.md)。core/solver官方基线为v2.4.0 commit `4426c6b499fc84920367f08853bfac2fa393e352`，正反向逐字节校验通过。旧 `aspect_pbr.diff` 是历史代表件，不是当前安装入口。

建议ASPECT 2.4.0、deal.II 9.3.2、Trilinos 13.2.0、p4est 2.2.0。本站实际源码在 `PBR/stepB/phase_index_20261017_codex/aspect_source`；`envs/aspect-2.4` 的solver/头文件不同，`envs/aspect-src` 为3.2.0-pre。不要依据目录名或mtime认定配套。新BUILD不得为build-pbr2/build-pbr3。

## 使用与回滚

从 `reproduce/` 目录按[主README](../../README.md)配置后，使用下述入口；不要手工再应用旧顶层diff。`build-sources.json` 是当前构建清单，`patches/stages/` 仅表示历史增量，不能叠加到完整补丁上。预检先检查全部目标、上下文和头文件，再写文件；重复执行当前版本不重复打补丁。

源码修改前保存 `source-backups` 与 `source_changes.json`。回滚按该清单恢复对应文件，或选择旧BIN/INSTALL；不reset整棵源码树、不删除旧输出。实际依赖、执行命令、已加载库和SHA256见build_report与execution JSON。版本为建议而非硬锁，未知源码上下文会明确停止。

```bash
bash scripts/build_aspect.sh NP=2
bash scripts/run_aspect.sh NP=1 CASE=blankenbach PROFILE=c1b PBR_ALIGN=on
bash scripts/run_aspect.sh NP=8 CASE=blankenbach PROFILE=c1b PBR_ALIGN=off
```

脚本构建匹配的Blankenbach/Tosi官方插件。C1b短窗End time=0.03，各460数据行；历史窗0.1/1626步不可混验。np1写trace.csv，MPI写trace.csv.rN。np1/np8的its不同属于进程数变化。on对齐同运行内状态，不保证跨运行重复。

包装选项为POLICY=off|fixed|online、K、BASE=100、UNIT=solve|step、COND=off|index。包装默认online；宿主原生未设PBR_POLICY时默认off，两者不要混同。COND=index需要assembly传入nonlinear_iteration，并配套当前头；不能再用“475/538行版本”判断。矩阵重置通知在core、计时/迭代回传在solver，三者都必需。历史关闭态等价性不构成当前任意MPI配置的逐位保证。

宿主与组合物的许可按该项目原声明执行；本项目自有部分见仓库LICENSE。
