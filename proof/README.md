# 第四章判据的 Lean 形式化核查

对象：`paper/draft_gemini/main.pdf` 第 13–16 页，重点是第 4.4 节命题 1 及其证明；同时核对了同目录的 `sec04_method.tex`。核查日期：2026-10-28。

## 结论

命题 1 的三项核心结论可以在明确的平稳、无噪声模型下成立。Lean 已检查成本差分、最大极小点、在线策略首周期至多延迟一步，以及其后每个周期均等于最优周期的通用证明。原文有两处需要修正：一个括号说明不成立，另一个证明分支使用了不成立的观测断言；后者可用保持同一预测的论证补全，不需要改变核心结论。

所有修改限于本目录。没有修改论文或实验程序。

## 运行

使用 Lean `4.35.0`，由 `lean-toolchain` 固定版本。依赖仅为该版本自带的 `Std`、`Init` 和 `Lean`，无需安装 mathlib，也不需要联网下载第三方证明库。

在本目录运行：

```powershell
lake build
lake env lean PreconditionerProof/Audit.lean
```

也可以运行 `verify.ps1`，它顺序执行上述两条命令，并在任一步失败时停止。

`Audit.lean` 会逐个检查项目定理的传递公理依赖。只允许 Lean 的标准逻辑基础 `propext`、`Classical.choice`、`Quot.sound`；出现 `sorryAx`、原生计算验证所引入的其他公理或自定义额外公理会失败。具体数值例子用 `decide +kernel` 检查，不依赖外部计算结果作为证明。

## 数学对象与显式前提

成本域是任意满足标准线性有序域公理的类型 `F`，并非仅验证有理数或有限组数据。证明只用有序域运算，不需要实数完备性；因此没有额外构造 mathlib 的 `ℝ`。有理数 `Rat` 用于实例化边界例子。

- `prefixSum n k` 为年龄 `0,...,k-1` 的累计复用求解成本。
- `cost ρ n k = (ρ + prefixSum n k) / k` 对应式 (7)。所有周期最优性结论均限制 `k ≥ 1`。
- `Nondecreasing n` 表示所有非负整数年龄上的单调不减。
- `DiscreteConvexFromOne n` 表示 `n(i+2) + (n(i+2)-n(i+1)) ≤ n(i+3)`，即年龄从 1 起的相邻斜率单调不减；不要求从年龄 0 起凸。
- `FirstTrigger ρ n K` 表示 `K ≥ 1`、`c(K) < n(K)`，且所有正年龄 `a < K` 均有 `n(a) ≤ c(a)`。
- `LargestMinimizer` 明确表达全体正整数周期上的全局最小值，以及所有达到相同最小值的周期都不超过 `K`。

在线学习部分明确使用以下理想化解释。这些是形式化模型的范围，不是已经从生产代码中验证的事实：

1. `n(a)` 不随物理时间或周期变化；基线恒等于 `n(0)`。
2. 重建费用 `ρ` 固定，运行平均使用的费用就是该 `ρ`，相当于 `ρ̂=ρ`。仅有迭代数无噪声不足以保证这条费用假设。
3. 已观测年龄形成 `1,...,m` 的前缀，观测值准确，并跨重建周期保留。预热留下的历史样本也必须符合相同平稳函数。
4. 已知年龄直接使用真实值；首次未知年龄使用最后两点的割线预测，零/一个已知年龄时分别使用基线/最近值。不存在额外的“同一年龄须累计若干样本才允许使用”门槛。
5. 每次先记录上一复用步，再决定下一步。触发重建时不执行旧预条件子在该年龄的复用求解，所以不获得该年龄的复用成本。

如果实际程序含有不同的样本保留、预热污染、最少样本数要求或变化的 `ρ̂`，不能直接把本证书解释为该程序行为的证明。

原文要求 `ρ ≥ 0`。通用代数及停止时间证明实际上不需要此限制，因而覆盖原文的非负费用情形；两个问题例子均使用严格正费用。

## 原文与定理对应

| 原文内容 | Lean 定理 | 已证明的范围 |
|---|---|---|
| 运行平均等于式 (7) | `running_average_eq_cost` | 从精确的累计费用递推得到等式 |
| 准确增量预测、非负裁剪 | `exact_prediction` | 单调老化下基线加裁剪增量等于真值 |
| 式 (8) | `cost_difference` | 任意正整数年龄的恒等式 |
| 判据等价于下一周期平均成本严格增加 | `trigger_iff_cost_increases` | 严格不等号的双向等价 |
| 严格触发点以后一直触发 | `trigger_persists` | 仅用单调不减，无需凸性 |
| 第 (ii) 项及平台右端点 | `first_trigger_exists`, `first_trigger_is_largest_minimizer` | 存在有限触发点时，首次触发是全局最大极小点 |
| 预测不高估、不会提前重建 | `current_prediction_upper`, `never_rebuild_early` | 显式在线模型及从年龄 1 起的离散凸性 |
| 至多延迟一步 | `rebuild_by_optimal_plus_one`, `cycle_bounds` | 第一停止位置必在 `{K,K+1}` |
| 直接在 K 停止后的状态保持 | `optimal_trigger_preserved` | 保留相同历史前缀，下一周期在 K 仍然触发 |
| 第 (iii) 项 | `all_later_cycles_optimal` | 任意合法无限执行中，所有后续周期均为 K |
| 排除不存在执行导致的空泛结论 | `cycle_exists`, `execution_exists` | 每个初始历史前缀都有停止周期和无限执行 |
| 三项核心结论的综合陈述 | `stationary_policy_correct` | 由单调、凸性和有限触发的前提得到最优性及收敛 |

通用定理及其辅助定理位于 `PreconditionerProof/Cost.lean` 和 `PreconditionerProof/Online.lean`。

## 保守外推变体（`PreconditionerProof/Conservative.lean`，2026-10-28 新增）

`Online.lean` 用线性割线外推预测未观测年龄，需要 `DiscreteConvexFromOne` 保证不高估（`current_prediction_upper`）。本文件改用**保守外推**：未观测年龄直接继承已知最大年龄的成本。此时单靠 `Nondecreasing` 即可证明不高估，凸性完全不需要。

| 结论 | 定理 | 已证明的范围 |
|---|---|---|
| 不高估 | `conservative_prediction_le` | 仅用单调性：`conservativePredict n (knownAt m a) a ≤ n a`（`0 < a`） |
| 不在 K 之前重建 | `conservative_never_rebuild_early` | 由上一条与 `FirstTrigger` 的既有前提直接推出 |
| 至多晚一步 | `conservative_cycle_bounds` | 周期长度必在 `{K, K+1}` |
| 此后锁定 | `conservative_stable_after_one_cycle` | 两种结束情形下在 `K` 处均触发 |
| 主定理 | `conservative_all_later_cycles_optimal` | **仅需 `Nondecreasing n` 与 `FirstTrigger ρ n K`**：首周期为 `K` 或 `K+1`，其余全部恰为 `K` |
| 非空性 | `conservative_cycle_exists` | 每个初始前缀都有停止周期，主定理不空泛 |

关键点：`DiscreteConvexFromOne` 在本文件中除文档字符串外**从未出现**。与 `stationary_policy_correct` 对比即可看出假设被去掉。

对应论文改动尚未执行。论文第 4.4 节的 (iii) 目前仍用割线外推，若改用保守外推，此文件即为其形式化依据；两处待修文字（下文第 1、2 条）在保守变体下同样适用，因为 `knownAt` 的语义未变。

验证记录见 `verification-linux-conservative.json`（Linux x86-64，Lean 4.35.0，151 条工程定理，公理限 `propext`/`Classical.choice`/`Quot.sound`，无 `sorry`）。

## 需要修正的两处文字

### 1. 没有严格触发，不等于没有有限最优周期

第 14 页命题 1 前提后的括号称：“否则 c(a) 单调不增，不存在有限的最优重建周期”。后一半不成立。

取 `ρ=1`、`n(0)=1`、`n(a)=2`（`a≥1`）。则对每个正整数 `k`，

```text
c(k) = [1 + 1 + 2(k-1)] / k = 2 = n(k).
```

没有任何严格触发点，但每个有限正整数周期都是最优周期。`no_trigger_but_every_finite_cycle_optimal` 对所有正整数给出形式证明，非仅枚举若干 k。

可以改为：“否则 c(a) 单调不增，严格判据不触发，也不存在最大的有限最优周期；有限最优周期是否存在，还取决于成本率是否最终达到平台。”其中“不存在最大有限极小点”已由 `no_trigger_no_largest_minimizer` 一般性证明。

这个例子不满足原命题的“存在严格触发点”前提，所以它反驳的是括号说明，不是该前提下的 (i)–(iii)。

### 2. 首周期在 K 直接重建时，未必观测了年龄 K

第 15 页证明中“若首个周期在年龄 K 处已触发重建，则此后全部所需年龄均已观测”，以及结尾对年龄 `1,...,K` 已完整观测的统一断言，在直接停止分支不成立。

取 `ρ=4`、`n(a)=a+1`。最优周期为 `K=3`。在线首周期的过程是：

- 年龄 1 的预测为 1，低于 `c(1)=5`，复用后观测 `n(1)=2`。
- 年龄 2 的预测为 2，低于 `c(2)=7/2`，复用后观测 `n(2)=3`。
- 年龄 3 的割线预测为 4，大于 `c(3)=10/3`，触发重建。

此时只观测了年龄 1、2，未观测年龄 3 的真实复用代价。`direct_stop_observation_gap` 同时证明 `K=3` 是最大极小点、策略确实在 3 首次停止，以及已知前缀仍为 2。

修复理由是：直接停止分支的历史前缀、基线和阈值在下一周期到达 K 时保持相同，因而相同的预测仍然触发。若首周期延迟到 `K+1`，这时才保证已经观测年龄 K，之后可以用真实值触发。`optimal_trigger_preserved` 与 `stable_after_one_cycle` 分别处理这两个分支。

因此，第 (iii) 项的结论在上述理想模型下得到保留，但原有证明文字应修正。

## 边界覆盖与验证边界

`Counterexamples.lean` 还检查了直接停止、延迟一步、`K=1`、最小值平台右端点四种精确有理数例子。它们辅助说明模型；通用最优性和所有后续周期的结论由独立的泛型定理证明。

此证书针对第 4.4 节的平稳理想模型和整数重建周期。它没有证明真实非平稳数据满足假设，没有证明在线估计器在噪声下的统计准确性，没有证明生产求解器源码与模型逐步等价，也没有验证整篇论文的实验结论。

## 来源指纹

- `main.pdf` SHA-256：`55D11C20546180344DE1C5A34D30C96FEBFC364066039BEBEE1DA10C6C19771D`
- `sec04_method.tex` SHA-256：`3A886F788BFD9AF05E92DDABF5DA10544C112F1AE523B51B19932382DCB77076`

论文更新后，应重新核对声明、假设与这些形式化定义的对应关系。
