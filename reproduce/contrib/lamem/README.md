# LaMEM 接入

使用LaMEM自己的 `pbr_policy.h`、`patches/lamem_lsolve_full_pbr.diff` 与 `patches/lamem_nlsolve_pbr_hooks.diff`。它沿用aspect::PBR命名空间，但不是ASPECT那份头文件；没有PBR_COND相位扩展。计时门控的真正接入点在lsolve.cpp，不只是头文件。

建议LaMEM 3.3.0、含MUMPS的PETSc及匹配MPI。Julia只用于Makefile可选checkgetrestore；显式make mode=opt lamem不依赖它，无Julia全量构建已验证。缺Julia警告不代表构建失败。

## 使用与回滚

从 `reproduce/` 目录按[主README](../../README.md)配置后，使用下述入口；不要手工再应用旧顶层diff。`build-sources.json` 是当前构建清单，`patches/stages/` 仅表示历史增量，不能叠加到完整补丁上。预检先检查全部目标、上下文和头文件，再写文件；重复执行当前版本不重复打补丁。

源码修改前保存 `source-backups` 与 `source_changes.json`。回滚按该清单恢复对应文件，或选择旧BIN/INSTALL；不reset整棵源码树、不删除旧输出。实际依赖、执行命令、已加载库和SHA256见build_report与execution JSON。版本为建议而非硬锁，未知源码上下文会明确停止。

```bash
bash scripts/build_lamem.sh NP=2
bash scripts/run_lamem.sh NP=8 PROFILE=c1b BASE=100 PBR_ALIGN=on
```

LaMEM是树内构建：为保护旧证据，先按主README复制源码树并设置PBR_LAMEM_SRC。必须核对execution JSON中的实际二进制路径/哈希；同大小或旧目录未更新mtime不能证明本次用了旧二进制。

C1b使用nstep_max=120、nstep_out=100000、BASE=100。原生策略模式为off/fixed/online，包装默认online；UNIT支持solve/step，主流程为solve。多进程日志pbr.csv.rN，单进程pbr.csv。

Rifting2D复用已知会线性达到50次上限，继而RC=83。C存档np8为8×134行/物理步32、np1为139行/步33；D0新构建np1/on曾153行/步34，不能保证固定失败位置。全部保留真实RC、失败类型、行数和失败步。不要调容差/规则来凑数。

跨运行翻转及新旧二进制的证据边界见主README第4节：C步np8三轮直接说明广播不保证跨运行重复；np1阈值数据不能误称同一二进制受控对比。旧“退出位置逐位相同”只对应历史观测，不能推广为普遍保证。

宿主与组合物的许可按该项目原声明执行；本项目自有部分见仓库LICENSE。
