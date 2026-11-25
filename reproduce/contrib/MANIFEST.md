# 当前交付与历史证据清单

本清单区分当前可构建的交付版本与产生历史论文数字的证据版本。2026-11-07实读文件生成指纹；行数只供定位，配套关系由内容/SHA256及build-sources.json确定。旧“475行/538行”论证不能用于当前文件。

## 1. 唯一构建入口与来源

读者调用scripts/build_<host>.sh，脚本以[build-sources.json](build-sources.json)为当前引入补丁清单。JSON登记目标路径、before/after SHA256和基线来源；源码预检/备份/幂等由scripts/lib/sources.py执行。已知当前文件直接接受，兼容版本按唯一精确上下文应用，未知改动明确拒绝。

- `*/patches/*full_pbr.diff`及JSON列出的接入补丁：干净上游→当前。MOOSE文件虽然名含alignfix，仍是干净上游→完整当前接入。
- `*/patches/stages/*.diff`：上一项目版本→下一版本，仅用于解释C1对齐/rank后缀/门控的历史增量，不在构建时重复叠加。
- 顶层 `aspect_pbr.diff`、`moose_pbr.diff`、`lamem_pbr.diff`、Elmer两个旧 `.pbr.diff`：保留的历史代表件，**不作为当前安装步骤**；不要与JSON指令混用。
- pbr_policy.h为项目新增文件，没有“官方原版”；直接交付各自当前头文件，不伪造一个通用的从无到有补丁。

ASPECT assembly基线来自交接.orig；core/solver基线为官方v2.4.0 commit `4426c6b499fc84920367f08853bfac2fa393e352`，已核每一处差异仅为PBR接入及其计时支持，官方+diff=当前、当前-diff=官方两向逐字节一致。其他完整补丁基线为交接包中PBR计数为0的.orig；原始来源与完整SHA256保存在JSON。

## 2. 当前交付指纹

不包含本清单自身及README，避免自引用；下表列出实际策略/接入文件，SHA256为完整值。

| 文件（相对contrib/） | 行数 | SHA256 | 角色 |
|---|---:|---|---|
| `aspect/aspect_pbr.diff` | 114 | `d65780bbde02d1f5e4762967179e99d5e812f645314e50aa66fbf8b1243aea80` | 历史代表件（不自动应用） |
| `aspect/patches/aspect_assembly_full_pbr.diff` | 62 | `315daa2294682453c5776506679b8acf4c1943f957b16f72d4969543864aea45` | 完整接入 |
| `aspect/patches/aspect_core_full_pbr.diff` | 19 | `0bc7e74194cb4553ab24ddda534ae4bf1c275f9ed4813fc15601b4c99eda4187` | 完整接入 |
| `aspect/patches/aspect_solver_full_pbr.diff` | 50 | `821878525431c4caa394011ae3fc88b7f9e8b2bcfe158d1145c289e6772da66a` | 完整接入 |
| `aspect/patches/stages/aspect_pbr_policy_c1_align.diff` | 114 | `69d88711101c1bc6d416a75b65235c31219cbff2c2f0d902f41ae7c74d0076d2` | 阶段增量（不自动应用） |
| `aspect/pbr_policy.h` | 606 | `e0376d06943bba2318650957d32957ce533f2e26b63e4394bd272a5e229bc5fd` | 当前专用头 |
| `build-sources.json` | 90 | `e54ada374004f51c3b24b1fa833a075177c59187d177fd0894594cadd8b1a0e0` | 构建清单 |
| `elmer/IterativeMethods.pbr.diff` | 26 | `5cb752bed00ba313c59885d45d03e12cb871c50b429ff0c883def22d6c2c33b6` | 历史代表件（不自动应用） |
| `elmer/IterSolve.pbr.diff` | 261 | `824e02b8d5ee3b1b1cbd47076a66d284c46e0080d50710bc15893be9bab2a489` | 历史代表件（不自动应用） |
| `elmer/patches/elmer_IterativeMethods_full_pbr.diff` | 26 | `5cb752bed00ba313c59885d45d03e12cb871c50b429ff0c883def22d6c2c33b6` | 完整接入 |
| `elmer/patches/elmer_IterSolve_full_pbr.diff` | 343 | `e06a703bf7fdacaed55dcee1bb2e2bbab2589b36f55001687d439936ba05c058` | 完整接入 |
| `elmer/patches/stages/elmer_IterSolve_aligngate.diff` | 42 | `ae68472470579fb97b61b542f23f9169395770b9240b41fbd657d24dce282451` | 阶段增量（不自动应用） |
| `lamem/lamem_pbr.diff` | 128 | `372d9b3c54cb7cb1fc27f4f27ec82b8f08da3034ce6217d2c5290e32f0eae0b9` | 历史代表件（不自动应用） |
| `lamem/patches/lamem_lsolve_full_pbr.diff` | 117 | `96994d20ba25075810a71c9ef4c8e119029b83ca3245df0142b99e7ed710a6f5` | 完整接入 |
| `lamem/patches/lamem_nlsolve_pbr_hooks.diff` | 18 | `f48618c41034ffdc77bc3e416c20a23d0bb8f995180ca3641d3f1b7c811a950a` | 完整接入 |
| `lamem/patches/stages/lamem_lsolve_aligntiming.diff` | 17 | `235033ff1d6e5045f43898ef49b6d627ee30947b8008a82048542a68f109c696` | 阶段增量（不自动应用） |
| `lamem/patches/stages/lamem_pbr_policy_ranksuffix.diff` | 23 | `aae88cbafd45e45ff05a3fe6c5e2a808b6b80334060fd3dba0a2bcda44275637` | 阶段增量（不自动应用） |
| `lamem/pbr_policy.h` | 460 | `7a5a758d690158d23fb828c8c7059a9b99900f9cdd08010c5d9ff6538b4dcb23` | 当前专用头 |
| `moose/moose_pbr.diff` | 102 | `94e4d43f66a4f8f1cc4be6464d9fbe29af8eb30d0af5a32037fdfc77b28b25dc` | 历史代表件（不自动应用） |
| `moose/patches/moose_NonlinearSystem_alignfix.diff` | 176 | `b039e1aec8aab638ac8e94bddc13f13ade11551af63de3084e3f8278b7b93877` | 完整接入 |
| `moose/pbr_policy.h` | 604 | `b8aa24601bbe32ced885b0044ff9a5f79e60d2f9231dfb3af00dd4c142c88732` | 当前专用头 |
| `openfoam-petsc/Make/files` | 3 | `92b944791a3e5d00f74bdc43b3125af7c33881b2e74375eb86b10de78ebca64e` | OpenFOAM插件/构建源 |
| `openfoam-petsc/Make/options` | 15 | `324025eaec9acaff962ee37e43b0c829331c1ec1bfa5911a914f142eefa5557c` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrDICFrozen/DICFrozenPreconditioner.C` | 700 | `8c54b326a1d55ce42ae9191ba6999ca5e5f5741de6f3fde4875bb644eef7afa8` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrDICFrozen/DICFrozenPreconditioner.H` | 113 | `783f1016965d3a293a423dec44edb4e66e3c58f99aee121a06d9816f3db845f5` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrDICFrozen/Make/files` | 3 | `5f605e524f16f9d8c8561683482799f4df7a2c2491bedc171fe7fc12f3cab0d1` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrDICFrozen/Make/options` | 2 | `882ee10c5cd1346a38a80c335d4c93a54de10f04ae486d841f3720d9d03d2f54` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrGAMG/Make/files` | 3 | `a0c40e7b2d94c2ef11aabd59a43ee0b3c15fbcc64a9b804e857c7f6141d38011` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrGAMG/Make/options` | 8 | `c34a8c4cba5ca478fcb40ace93da2960118b63aebaed8d1af3f8457ed8c63a31` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrGAMG/PBRGAMGPreconditioner.C` | 285 | `5ea6532d84e21974a6092a74dc87330bc783c729689b5f9febdc62b9ee24c8b8` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrGAMG/PBRGAMGPreconditioner.H` | 143 | `1041946f4ead6e11df40ce6c51ea6b5955ac4f4e70be4e522da19b96a9b962c9` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrSolverTimer/Make/files` | 4 | `6f2c42c521cb8dd71fd380c74c84aecb7395d84dc5a78e708a2635f240dfa6a1` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrSolverTimer/Make/options` | 8 | `c34a8c4cba5ca478fcb40ace93da2960118b63aebaed8d1af3f8457ed8c63a31` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrSolverTimer/PBRPCG.C` | 184 | `6d26bf7953c95824d2041e23b62fcbbc0542267f3f5598d1a5cb5d1a691f3845` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrSolverTimer/PBRPCG.H` | 110 | `6b9f01beb166882fe7da6ae88b4503c9a87c8b728b2de337644947a1efde5573` | OpenFOAM插件/构建源 |
| `openfoam-petsc/pbrSolverTimer/PBRPCGReport.C` | 38 | `8d7c659d1fcfdd2cd0c62d6f04cd56f8867d8d4ef1379a5841e87a47d2193840` | OpenFOAM插件/构建源 |
| `openfoam-petsc/PETScPreconditioner.C` | 1214 | `00b0c5d0567319f17793234369e3ed20b141c3c52c9954fa06341445261e1dce` | OpenFOAM插件/构建源 |
| `openfoam-petsc/PETScPreconditioner.H` | 302 | `f2298e9c0ed6395aba910de8a3f9a23170526f51007675c5401c891623b49c51` | OpenFOAM插件/构建源 |

## 3. 为何四宿主实现不合并

| 宿主 | 当前区别与配套点 |
|---|---|
| ASPECT | 专用C++头，PBR_COND；assembly传入nonlinear_iteration，core通知矩阵重置，solver回传迭代/计时；rank后缀与PBR_ALIGN在头中 |
| MOOSE | 独立C++头，PBR_COND及诊断列；SNES上下文传j；NonlinearSystem中的ALIGNFIX由ALIGN门控，集体OR修复本地KSP指针谓词 |
| LaMEM | 独立C++头，无PBR_COND；lsolve的alignDouble替换裸dt广播，保留off的本地计时；nlsolve安装钩子 |
| Elmer | 独立Fortran实现；AlignAny修复首建谓词；IterativeMethods补GCR实际迭代计数，不能用C++头代替 |
| OpenFOAM | 插件自含策略；PETSC_COMM_SELF局部PC，无PBR_ALIGN；允许rank日志后缀，与共享PC广播不同 |

三处C步集合通信修复未改est/avg判据公式，但改变了集合执行动作和LaMEM off臂计时语义；**不能声称所有历史轨迹完全不变**。当前版本的独立验证不能自动替代旧证据批次。

## 4. 历史来源与适用范围

历史文件不删除，现行入口不再让读者按旧“475版可替代528版”说明操作。旧清单中的16ed56…、595707…及相应行数描述的是此前文件，不能作为当前交付的配套依据，也不能给全部论文表格统一套用当前哈希。下表保留历史来源；遇到历史数字应以对应运行/构建档案为准，历史版本的等价性结果不因当前文件升级而被撤回，也不自动外推到新版本。

| 证据/阶段 | 来源 | 当前交付能声明的范围 |
|---|---|---|
| 10月论文主结果、Blankenbach/Tosi、Elmer与OpenFOAM批次 | 仓库docs中各实验记录，服务器各原运行目录；ASPECT build-pbr2等旧构建 | 当前C1b实现不是所有历史实验的同一个二进制；不重新给旧数字挂当前哈希，不改§7或expected |
| 相位扩展（Step B / t43） | stepB/phase_index_20261017_codex、docs/stepB相关记录、原build-pbr3时期产物 | 当前ASPECT/MOOSE仍保留相位扩展接口；相位观测与集体通信改动按阶段溯源，不凭475行声称配套 |
| 10-29/30关闭态等价性 | docs/lamem_pbr_equivalence_20261029.md、reproduce_coverage_20261030.md及旧运行 | 属于其当时版本/输入的实测；不外推为当前任意MPI配置均逐位等价 |
| C1b正式四宿主 | docs/handoff/c1b_source_20261107，c1b_*专项记录，服务器c1b_elmer/c1b_aspect | 当前三份头与交接当前文件一致；Elmer与接入补丁按JSON的after哈希追溯 |
| D0入口和依赖验证 | docs/d0_server_verify_codex_20261107.md、d0_stage3_gaps_codex_20261107.md及d0_reproduce产物 | 新入口经过A/B/C/D核查；LaMEM有一个C档不匹配；不是恢复原始launcher，也不是重新测论文性能 |

LaMEM/ASPECT/Elmer原始C步MPI命令未归档。现行脚本由早期lamrun.sh、elmrun2.sh、run9fix.sh、lamembuild_c1b.sh、elmerbuild_c1b.sh及dealenv/elmerenv配置重建。MOOSE原脚本有档案；不把当前站点选择倒写为其他宿主的历史命令。

ASPECT三个源码树区别与正确构建路径见主README：实际C源码为stepB的aspect_source；envs/aspect-2.4不是同一版本内容；envs/aspect-src是3.2.0-pre。官方2.4.0基线与上述当前源码树也不是一个概念。

LaMEM np1/on的139→153行对比使用不同哈希二进制（旧5dbb0be7…，D0新f2dbbaf6…）；不能因旧目录mtime未变便称未重编。C步np8三轮的跨运行翻转仍是广播不能保证重复性的证据。

## 5. 服务器目录分类（不执行清理）

以下均相对/root/autodl-tmp/PBR，另注明者除外。

| 类别 | 路径 | 处置 |
|---|---|---|
| 证据 | c1b_elmer/c1b_np8_r*、c1b_lamem_r*、c1b_elmer_np8*；c1b_aspect/gb_r*；相关status/patches | 保留原始运行与输入，不覆盖 |
| D0工程验证 | d0_reproduce/codex_verify_20261107、codex_gaps_20261107、reader_*及独立builds/upstream | 不是新科学面板；保留验证记录与失败实例 |
| 旧证据二进制/库 | /root/autodl-tmp/envs/aspect-2.4/build-pbr2、build-pbr3；旧宿主构建；/root/OpenFOAM/root-v2406/platforms/.../lib/libpbr{PETSc,SolverTimer}.so | 不覆盖；另选BUILD/INSTALL/输出库路径 |
| 候选可清理诊断产物 | c1b_elmer下diag_*、verify_*、timing_*、np2_*、meshpart*、np4_geo、np8_geo、smoke_*等 | 仅为类别，不是删除授权；清理前另行批准 |
| 受保护历史数据 | /root/autodl-tmp/CFD_checkpoints*、CFD_debug_outputs、/root/GMRES-Learning-main*及旧归档 | 不触碰 |
| 范围外历史研究 | 其他*_case、*_store、w*/k*/l*/s*等历史目录、仓库docs/data/code开发档案 | 不纳入本轮整理 |

## 6. 许可与回滚

本项目自有策略实现见仓库LICENSE；上游源码、补丁上下文和算例版权仍属各宿主，组合物遵从相应许可。构建不需要分发完整上游源码。回滚按job/source_changes.json与source-backups恢复指定文件，MOOSE另有library-backups；切换以前的BIN/INSTALL可回退运行环境。保留新旧证据，不reset或clean整棵树。
