# 预条件子重建策略：复现入口

本目录提供五条构建与运行路径。宿主源码和依赖由读者预先安装；本包负责接入策略、选择环境、生成运行副本和记录结果。先从 OpenFOAM 的串行固定周期验证开始，再选择所需宿主。项目说明见根 README；当前补丁及历史来源见 [contrib/MANIFEST.md](contrib/MANIFEST.md)。

**运行完成、计数匹配、参考精度通过是三个独立结果。** `PBR_ALIGN=on` 用于同一次运行内各 rank 对齐，不能保证跨运行重复。LaMEM 存在预期的求解失败和跨运行动作变化；Elmer 的 np8 入口能完成，但参考精度 FAILED。不要为了对齐数字更改 `expected/`、求解器设置或判据参数。

## 1. 依赖与配置

需要 Linux、Bash 4+、Python 3.8+、对应宿主的编译工具链，以及与其实际加载库匹配的 MPI。以下为**建议版本（我们所用）**，不是版本相等的准入条件；换版本需重新检查 API、输入和计数可比性。

| 宿主 | 建议版本 | 预先准备 |
|---|---|---|
| OpenFOAM | OpenCFD v2406、PETSc 3.25.1 | OpenFOAM 的 wmake/编译工具、PETSc、MPI；脚本会编译 libpbrPETSc 和必需的 libpbrSolverTimer |
| MOOSE | 交接对应源码、moose-env 的 PETSc/libMesh/WASP、Open MPI 5.0.10 | 可构建的 MOOSE 源码树及匹配依赖；Darcy step06 应用 |
| LaMEM | 3.3.0、PETSc（含 MUMPS） | C++17 编译器、PETSc、MPI；Julia 只用于可选 checkgetrestore |
| ASPECT | 2.4.0、deal.II 9.3.2、Trilinos 13.2.0、p4est 2.2.0 | 完整 ASPECT 源码，含官方 Blankenbach/Tosi 插件源码及上述库 |
| Elmer/Ice | 26.2、WITH_MPI=TRUE | Fortran/C/C++、MPI、BLAS/LAPACK、该源码所需依赖；独立安装前缀 |

配置优先级：**命令行 KEY=VALUE > 已导出的环境变量 > config/site.local.sh > 显式选择的站点配置 > config/site.sh 默认值**。`site.sh` 不含 AutoDL 路径；`PBR_SITE=autodl` 才加载 `site.autodl.sh`。`site.local.sh` 用于个人路径，不存凭据。不要在调用 run 脚本前另外手工 source 多套宿主环境。

其他机器先在 `config/site.local.sh` 为要使用的宿主填写：

```bash
# 模板：替换路径；仅配置选中的宿主，无需五套全装。
PBR_ASPECT_SRC=/path/to/aspect-source
PBR_ASPECT_DEAL_II_DIR=/path/to/deal.II/cmake
PBR_ASPECT_MPIEXEC=/matching/mpi/bin/mpirun
PBR_ASPECT_MPICC=/matching/mpi/bin/mpicc
PBR_ASPECT_ENV_PATH=/matching/toolchain/bin:/usr/bin:/bin
PBR_ASPECT_LD_LIBRARY_PATH=/matching/dependencies/lib
```

每宿主独立字段为 `PBR_<HOST>_{SRC,BUILD,INSTALL,BIN,MPIEXEC,MPICC,ENV_PATH,LD_LIBRARY_PATH,PETSC_DIR,PETSC_ARCH,OMPI_CC,OMPI_CXX,OMPI_FC}`；HOST 为 MOOSE/LAMEM/ASPECT/ELMER/OPENFOAM。`PBR_<HOST>_ENV_MODE=prefix|conda|micromamba|module|hook|existing` 配合该宿主的 `ENV_PREFIX`、`ENV_SCRIPT`、`ENV_MODULE` 字段使用（均需 `PBR_<HOST>_` 前缀）。MOOSE 另需 `PBR_MOOSE_LIBMESH_DIR`、`PBR_MOOSE_WASP_DIR`，或让 `PBR_MOOSE_ENV_PREFIX` 指向包含它们的环境；OpenFOAM 设置 `PBR_OPENFOAM_BASHRC`；Elmer 可用 `PBR_ELMER_CMAKE_ARGS` 指定本站 BLAS/LAPACK。`PBR_<HOST>_CMAKE_ARGS`、`PBR_<HOST>_MPI_ARGS` 每行一个完整参数，不是 shell 表达式。`bash scripts/build_aspect.sh --help` 可查看共同接口。

`NP` 默认取 min(8, 可用核数)，会考虑 CPU affinity/cgroup；实际值记录在 `resources.json` 和 `configuration.json`。OpenFOAM 的并行输入固定为四分区，必须显式 `NP=4`；串行显式 `NP=1`。`THREADS=1` 同时限制 OpenMP/BLAS 线程。`JOBS` 是编译并发数，不是 MPI rank 数。

## 2. 一次完整的本站操作流程

下面各块在**同一个 Bash 会话**按顺序执行，`# verify:` 只是逐字验证时的块名。此路线使用已经安装好的宿主/依赖，从新输出目录开始，绝不要求重新安装操作系统或依赖。MOOSE 和复制后的 LaMEM 树可使用已有编译缓存；ASPECT、Elmer、OpenFOAM 使用本次新构建目录。其他机器将第一块的站点与路径替换为自己的配置，再执行所选宿主的块。

### 2.1 新会话与输出位置

```bash
# verify: setup
set -euo pipefail
cd /root/autodl-tmp/PBR/d0_reproduce/src/reproduce
export PBR_ROOT="$PWD" PBR_SITE=autodl
export PBR_PYTHON=/root/miniconda3/bin/python3
export PBR_OUTPUT_ROOT=/root/autodl-tmp/PBR/d0_reproduce/reader_$(date +%Y%m%dT%H%M%S)
export PBR_BUILD_ROOT="$PBR_OUTPUT_ROOT/builds"
export THREADS=1 JOBS=2 KILL_AFTER=5 BUILD_TIMEOUT=1800 TIMEOUT=1800
export POLICY=online BASE=100 UNIT=solve COND=off PBR_ALIGN=on PBR_ALIGNFIX=on
mkdir "$PBR_OUTPUT_ROOT"
printf '本次输出：%s\n' "$PBR_OUTPUT_ROOT"
# LaMEM 是树内构建：复制到数据盘新目录，保留原 C 步二进制。
mkdir "$PBR_OUTPUT_ROOT/sources"
cp -a /root/autodl-tmp/envs/lamem/src "$PBR_OUTPUT_ROOT/sources/lamem"
export PBR_LAMEM_SRC="$PBR_OUTPUT_ROOT/sources/lamem"
```

`RUN_DIR` 必须是尚不存在的目录，重复同名会明确退出，不清理旧输出。本流程顺序执行，最多 8 个求解 rank；不要同时启动所有宿主。本站容器内存上限约 62 GB，不是 `free` 显示的物理宿主总内存；约定并发占用不超过 40 GB，单进程预计超过 8 GB 或单次超过 30 分钟时先评估资源。构建/输出均放数据盘。

### 2.2 首次环境自检

```bash
# verify: environment-before
if bash scripts/verify_environment.sh NP=8 PBR_VERIFY_SMOKE=0 RUN_DIR="$PBR_OUTPUT_ROOT/environment_before"; then
  printf '初次环境检查完成\n'
else
  printf '检查 environment_before：新构建尚不存在时会明确报缺二进制/库；先确认已安装的宿主依赖，再执行构建。\n'
fi
```

新输出前缀内的库尚未构建，首次检查可能非零；这不能记成完整环境通过。缺少宿主、编译器或依赖时先按对应错误配置，不能忽略后续构建失败。只检查某个宿主可加 `PBR_VERIFY_HOST=openfoam` 等。最后还有一次带真实双 rank 集合通信的检查。

### 2.3 OpenFOAM：构建 → 串行 expected → 四进程

```bash
# verify: openfoam
bash scripts/build_openfoam.sh NP=2 BACKGROUND=1 RUN_DIR="$PBR_OUTPUT_ROOT/build_openfoam"
"$PBR_PYTHON" scripts/lib/pbr.py job wait "$PBR_OUTPUT_ROOT/build_openfoam" --wait 1800 > "$PBR_OUTPUT_ROOT/build_openfoam.wait.log"
bash scripts/run_openfoam.sh NP=1 PROFILE=historical CFG=fx MODES=K1 ROUNDS=1 CHECK_EXPECTED=1 RUN_DIR="$PBR_OUTPUT_ROOT/openfoam_np1"
bash scripts/run_openfoam.sh NP=4 PROFILE=historical CFG=fx MODES=K1 ROUNDS=1 CHECK_EXPECTED=0 RUN_DIR="$PBR_OUTPUT_ROOT/openfoam_np4"
```

串行本站参考：**344 个时间步（也是 344 个重建步）、7957 次迭代、1031 次累计预条件子重建**。一个时间步可以有多次重建，344 与 1031 不能混称。`result.json` 应给出 `expected_match=true`。并行本站参考是 343 步/1028 次累计重建，四份 `pbr_pc.csv.r0`–`.r3`，无 FATAL；不得用串行 expected 硬判并行结果。

OpenFOAM 的 PBR 是 `PETSC_COMM_SELF` 上的局部 PC，**没有 PBR_ALIGN 对齐开关**。rank 日志/快照分目录是文件隔离，不是广播同一个全局 PC 决策。脚本沿用自带 `decomposeParDict`，不现场改分区数。两份必要插件输出到本次 `builds/openfoam/lib`，不覆盖旧证据库。

### 2.4 MOOSE：构建与 np8 两臂

```bash
# verify: moose
bash scripts/build_moose.sh NP=8 BACKGROUND=1 RUN_DIR="$PBR_OUTPUT_ROOT/build_moose"
"$PBR_PYTHON" scripts/lib/pbr.py job wait "$PBR_OUTPUT_ROOT/build_moose" --wait 1800 > "$PBR_OUTPUT_ROOT/build_moose.wait.log"
for arm in on off; do
  bash scripts/run_moose.sh NP=8 PROFILE=c1b PBR_ALIGN="$arm" RUN_DIR="$PBR_OUTPUT_ROOT/moose_np8_$arm"
done
```

构建脚本在 MOOSE 自己的应用树构建，先备份 `libmoose-opt.so*` 到本次 build job 的 `library-backups`。源码变化前也保留 before-image。需要保持旧安装完全只读的读者应另配源码树。运行自动加入官方 `Executioner/reuse_preconditioner=true` 和 `reuse_preconditioner_max_linear_its=1000000`，两臂一致使用。参考为每臂八份 `pbr.csv.rN`、各819数据行、各2721次迭代。`PBR_ALIGNFIX=on` 与 `PBR_ALIGN` 是门控关系：只有 ALIGN 也为 on 时才执行集体 OR，绝不是互斥选项。

### 2.5 ASPECT：新构建与单/多进程

```bash
# verify: aspect
bash scripts/build_aspect.sh NP=2 BACKGROUND=1 RUN_DIR="$PBR_OUTPUT_ROOT/build_aspect"
"$PBR_PYTHON" scripts/lib/pbr.py job wait "$PBR_OUTPUT_ROOT/build_aspect" --wait 1800 > "$PBR_OUTPUT_ROOT/build_aspect.wait.log"
for ranks in 1 8; do
  bash scripts/run_aspect.sh NP="$ranks" CASE=blankenbach PROFILE=c1b PBR_ALIGN=on RUN_DIR="$PBR_OUTPUT_ROOT/aspect_np$ranks"
done
```

脚本同时构建官方 Blankenbach/Tosi 插件；必须与所选 ASPECT 构建配套，不能只复制一个未知来源的 `.so`。本站三棵树必须区别：

| 路径（/root/autodl-tmp/ 下） | 性质 |
|---|---|
| `PBR/stepB/phase_index_20261017_codex/aspect_source` | 2.4.0，C 步实际源码；本站配置使用它 |
| `envs/aspect-2.4` | 也是2.4.0；core相同、solver不同，策略头也是另一代，不能当作相同源码 |
| `envs/aspect-src` | 3.2.0-pre，不是2.4.0补丁的官方基线 |

从官方2.4.0干净源码接入时，由 `build-sources.json` 指定三份完整 diff 和配套头文件。`core/solver` 基线为官方 v2.4.0 commit `4426c6b499fc84920367f08853bfac2fa393e352`，正反向逐字节验证已完成。预检检查源码/补丁上下文和头文件配套，不凭目录名推断正确，也不把所有其他版本一律拒绝；上下文不兼容时停止，不能自动跳过补丁。旧 `build-pbr2/build-pbr3` 不可作为新构建目录。

`PROFILE=c1b` 的 End time 为0.03，参考460数据行/461含表头。np1写 `trace.csv`，np8写八份 `trace.csv.rN`；本站总迭代分别11876/11047。`PROFILE=historical` 使用0.1，其1626步历史参考不能套到短窗。并行输入不启用不支持 MPI 的 `temperature ascii out` 后处理器。此处不重跑 Tosi 或论文完整面板。

### 2.6 Elmer：构建、install、几何分区

```bash
# verify: elmer
bash scripts/build_elmer.sh NP=2 BACKGROUND=1 RUN_DIR="$PBR_OUTPUT_ROOT/build_elmer"
"$PBR_PYTHON" scripts/lib/pbr.py job wait "$PBR_OUTPUT_ROOT/build_elmer" --wait 1800 > "$PBR_OUTPUT_ROOT/build_elmer.wait.log"
bash scripts/run_elmer.sh NP=8 PROFILE=c1b PBR_ALIGN=on RUN_DIR="$PBR_OUTPUT_ROOT/elmer_np8"
```

脚本必须完成 `cmake --install`，并验证**实际加载**本次 INSTALL 下的 `libelmersolver.so`；不能只看编译 RC、可执行文件或库的 mtime。运行选择 `stabilized.sif` 的 Stokes-Vec Solver 2，自动写启动信息、PBR开关和计时选项，不能使用原 STARTINFO 指向的另一个 sif。

几何分区命令为 **`ElmerGrid 2 2 mesh2D -partition N 1 1`**。三个方向都要写。少写最后一个1会打印 `The number of partitions in 3 dims is required as parameters.`，却返回RC=0且不生成目录；脚本另验分区目录，不能只验RC。np8参考为40个分区文件、每rank271数据行/20490迭代。本站分区已与C存档40文件逐字节匹配。

在本站复核 A 档时，将本次 `$PBR_OUTPUT_ROOT/elmer_np8/case/mesh2D/partitioning.8/` 与 `/root/autodl-tmp/PBR/c1b_elmer/c1b_elmer_np8_on/mesh2D/partitioning.8/` 的相对文件名及逐文件 SHA256 比较；两边均为40文件且映射完全相同才记为逐字节一致。历史分区不随本包分发，其他机器没有该归档时应将 A 档记为“未检”，不能凭40这个数量判相同；B档计数和参考精度仍分别检查。

该MPI入口用于核查接口，**不推荐作为该算例的精度复现路径**：np8参考误差 **6.178587E-06 > 1E-06，FAILED**，即使RC=0/ALL DONE也必须保留。几何分区方式与进程数效应未被单独分离，不把迭代数上升全部归于核数，不改容差追求PASSED。

### 2.7 LaMEM：无 Julia 构建，保留预期 RC=83

```bash
# verify: lamem
bash scripts/build_lamem.sh NP=2 BACKGROUND=1 RUN_DIR="$PBR_OUTPUT_ROOT/build_lamem"
"$PBR_PYTHON" scripts/lib/pbr.py job wait "$PBR_OUTPUT_ROOT/build_lamem" --wait 1800 > "$PBR_OUTPUT_ROOT/build_lamem.wait.log"
lamem_rc=0
bash scripts/run_lamem.sh NP=8 PROFILE=c1b PBR_ALIGN=on BASE=100 RUN_DIR="$PBR_OUTPUT_ROOT/lamem_np8" || lamem_rc=$?
printf 'LaMEM 原始返回码=%s；参考是83，仍表示求解失败\n' "$lamem_rc"
[[ "$lamem_rc" == 83 ]]
```

Julia只在Makefile的可选 `checkgetrestore` 静态检查中调用；`lamem : lamemlib linkexe` 不依赖它。无Julia、无旧对象文件的全量构建已实测成功，缺Julia时构建脚本警告并继续显式 `lamem` 目标；不运行可选静态检查。

`PROFILE=c1b` 设置 `nstep_max=120`、`nstep_out=100000`，保留官方求解器参数。该复用运行往往提前在 `DIVERGED_ITS iterations 50` 后返回83；参考np8为8×134 CSV行/物理步32，但该结构并非跨运行保证，见第4节。结果中 `simulation_complete=false` 是真实结果，不能把83改为0。这里仅运行一臂用于入口验收；不重复三轮实验。

### 2.8 构建后环境检查与结果读取

```bash
# verify: environment-after
bash scripts/verify_environment.sh NP=8 PBR_VERIFY_SMOKE=1 RUN_DIR="$PBR_OUTPUT_ROOT/environment_after"
"$PBR_PYTHON" - <<'PY'
import json,os
from pathlib import Path
root=Path(os.environ['PBR_OUTPUT_ROOT'])
for p in sorted(root.glob('*/result.json')):
    d=json.loads(p.read_text())
    print(p.parent.name,{k:d.get(k) for k in ['solver_returncode','simulation_complete','expected_match','reference_accuracy','trace_complete','same_rank_decisions','timing_columns_identical','steps','total_its','total_builds']})
    print('traces',[(Path(t['file']).name,t.get('data_rows'),t.get('total_its'),t.get('decision_rebuilds'),t.get('total_builds')) for t in d.get('traces',[])])
PY
```

`configuration.json/runtime.json` 记录实际参数，`inputs.json` 记录输入及最终分区文件指纹，`execution-*.json` 记录真正执行的命令/二进制/RC；`build_report.txt` 记录源码、加载库、环境与SHA256，`result.json` 分开报告完成、计数和精度。每个rank的its是同一次全局求解的计数，**不能把八份相同its再求和**。

## 3. 验收分 A/B/C/D 四档

| 档 | 核查量 | 本站已知参考与范围 |
|---|---|---|
| A 逐字节 | 文件内容完全相同 | Elmer相同几何分区的40文件；不是所有运行日志都要逐字节相同 |
| B 确定性计数 | 相同环境/输入/进程数下的计数 | MOOSE np8各2721；Elmer np8各20490；OpenFOAM fx/K1串行7957迭代、344步、1031累计重建 |
| C 结构性 | 失败类型、位置、行数、RC分别核对 | LaMEM C存档np1 1×139行/步33；np8 8×134行/步32；全为83。但D0已有np1/on 153行/步34的不匹配实例，必须记录而非强行判一致 |
| D 预期不同 | 改变进程数后的求解行为 | ASPECT g1/g8的its不同；OpenFOAM np4 343步/1028构建，不拿串行344/1031硬判 |

**运行完成 / 计数匹配 / 参考精度**单列，不把四档合并成一个“通过”。on臂应同运行内rank决策一致；off臂不要求每一行计时都不同，整列完全相同才值得排查。off也不分歧不能证明机理上不可能分歧。

`expected/` 是冻结的、**带环境条件的历史参考**。其中“必然逐位对上”“对不上就是配置问题”等旧措辞限于对应的同环境历史批次，不适用于跨版本、跨进程数、不同物理窗或所有计时驱动的在线运行。不要改expected来适配新输出。只有支持的串行固定策略使用 `CHECK_EXPECTED=1`；在线或MPI用分档核查，不能仅凭一项计数差异诊断入口错误。绝对墙钟不能跨机器/跨批直接比，本流程不测加速比。

## 4. 三种现象及跨运行翻转实证

**跨运行变化。** LaMEM的计时观测进入运行平均代价，严格比较 `est > avg`。C步np8三轮在求解序号129处，on臂动作是0/1/1，off是1/0/1；est=9，avg约8.75–9.08，余量0.25%–2.8%。on臂本身也跨轮翻转，说明rank 0广播只能使本次运行各rank采用一致观测/决策，不能令下一次运行重复。它是计时驱动策略的已观察现象，不应仅凭翻转认定入口bug，也没有“调参即可稳定”的结论。

D0入口验证另记录了np1/on的变化：

| 量 | C步r1 | D0新构建运行 |
|---|---:|---:|
| 第113号求解est | 7 | 7 |
| avg | 6.97586 | 7.00324 |
| rebuild | 1 | 0 |
| CSV行数（含表头） | 139 | 153 |
| 失败物理步 | 33 | 34 |

**这组np1对比不能称为“同一二进制”的受控证据。** 执行记录确认D0使用独立全量新编译 `lamem_clean/bin/opt/LaMEM`（SHA256 `f2dbbaf6…`）；旧树二进制为 `5dbb0be7…`。两者同为1480336字节并不代表内容相同。输入数值一致、注释不同，D0另加 `-log_view`；未分离新编译、计时选项与负载影响。表中阈值翻转是实测，不能把全部差异只归因于计时噪声。广播的跨运行局限由前述C步np8三轮直接支撑。

相反，在C步所测配置与三轮范围内，MOOSE、ASPECT、Elmer的on与off**各自**跨轮稳定；不能归功于广播，因为off也稳定。观测支持这些配置的决策余量较宽，不保证其他算例/环境也稳定。

**换进程数变化。** ASPECT g1/g8和OpenFOAM串行/np4改变了并行分解及求解行为，是另一类比较；本包没有把它当作缩放研究。Elmer还存在分区方式与进程数效应未分离的限制。

**启动配置错误。** 错MPI、错sif、不生成trace属于配置问题，不能用“结果可能不同”掩盖。LaMEM/ASPECT/Elmer的C步原始MPI命令未归档；当前入口按早期骨架和实际配置重建，并作A/B/C/D反验证，不能称为找回原命令。读者无需依赖旧手工脚本。

## 5. 排障、后台管理与保护

| 症状 | 检查与处置 |
|---|---|
| `pmix_value_load` 未定义 | 系统Open MPI 4.1.2的组件可能加载了conda OpenPMIx 5.0.8；让宿主启动器、实际libmpi、PMIx环境同源，检查显式LD_LIBRARY_PATH。不要修系统库、统一换conda或用 `--mca pmix ^ext3x` 掩盖；后者真实双rank测试曾段错误 |
| `libpmix.so.2.5.2` | 文件名属于ABI/库命名，不是PMIx软件版本；用 `PMIx_Get_version()` 或可靠版本字符串核实。本站系统实际是OpenPMIx 4.1.2 |
| `Unknown solver type PBRPCG` | 缺少或没加载libpbrSolverTimer；build_openfoam会同时编译两库 |
| `Unknown ... PETScILU` | 先查实际插件和PETSc依赖库是否解析成功，不要直接改fvSolution |
| Elmer RC=0但无trace | 检查实际加载的libelmersolver、stabilized.sif的Solver 2、PBR_LOG及分区目录 |
| MOOSE `Reference HEAD is not valid`、随后make注明`ignored` | 缺Git元数据的源码快照可能触发版本标签生成警告；查看后续真实构建、链接、MPI和运行结果，不据此猜版本。本次本站增量构建出现该警告，后续运行完成且计数匹配 |
| ASPECT缺Trilinos库/插件 | 配置宿主专用库路径，使用匹配构建的官方插件，不串用三棵树 |
| `Missing command` / MPI版本不匹配 | 补依赖或修宿主专属配置；版本建议不是硬锁，但启动器/已加载MPI必须兼容 |

本站配置当前选择：MOOSE→moose-env MPI 5，LaMEM/OpenFOAM→base conda MPI 5，ASPECT/Elmer→系统MPI 4；这是当前加载库核验结果，不倒写为全部历史launcher事实。

`BACKGROUND=1` 立即返回只表示已启动；实际工作在 `RUN_DIR/worker/`。用 `"$PBR_PYTHON" scripts/lib/pbr.py job status JOB_DIR` 查询，`job wait JOB_DIR --wait 30` 等待（124可仅表示等待窗口结束，需再查状态），`job stop JOB_DIR --grace 5` 只停止该job记录的自有进程。不要用 `pkill -f`、不要结束别人的orted。监督器先TERM、超时后KILL；直接临时使用timeout也必须带 `-k 5`，因为mpirun可能忽略TERM。

源码补丁预检及幂等由 `build-sources.json` 驱动，不能再手工重复应用顶层旧diff或stages增量。`contrib/README.md` 的旧配套说法与 OpenFOAM 子目录旧手工示例不是现行操作步骤；使用本页脚本和当前 MANIFEST。回滚选择以前的BIN/INSTALL/库路径；源码回滚按 `source_changes.json` 恢复本次 `source-backups`，不对整棵树reset/clean。保留输出、证据和备份，不删除服务器文件；清理另行取得批准。不得覆盖旧OpenFOAM证据库或ASPECT build-pbr2/build-pbr3，不读取/上传凭据。

## 6. 文件与许可

`config/`配置；`scripts/`构建/运行/检查；`contrib/`宿主各自的策略与补丁；`cases/`输入；`expected/`冻结参考。ASPECT/MOOSE/LaMEM三份C++头与Elmer独立Fortran实现故意保留差异，不合并通用文件。历史开发记录在仓库docs中，不是运行前置条件。

项目自有代码遵循仓库LICENSE；宿主、补丁上下文和官方算例的版权归原项目，应用后组合物遵循宿主许可。算例来源见各cases目录的SOURCE/README。ASPECT官方插件源码不随本包复制，build_aspect从读者选择的完整官方源码树构建。
