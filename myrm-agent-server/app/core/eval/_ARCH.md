# app/core/eval 模块架构


---

## 架构概述

`eval` 模块是 Myrm Agent Server 提供的 Agent 评估与回归测试的核心业务引擎。它作为 `myrm_agent_harness/eval` 框架层的具体实现，负责桥接框架的 `AgentExecutor` 协议和 Server 的 `AgentFactory` 业务逻辑。

## 核心设计原则

1. **单机沙箱策略**：评估用例和报告均持久化在用户专属的本地 `.myrm/` 目录下，不依赖外部数据库。
2. **异步非阻塞**：评估套件的执行可能非常耗时，因此采用异步后台任务（BackgroundTasks）运行，通过内存状态字典（`_eval_state`）提供实时的进度查询。
3. **引擎解耦**：本模块不关心具体的断言逻辑（由 Harness 层负责），只负责提供执行环境和生命周期管理。

## 文件清单

| 文件 | 职责 |
|------|------|
| `adaptive.py` | 并发让出基础设施：`mark_chat_activity`（前台 ChatService 心跳）+ `AdaptiveEvalManager`（评测后台任务检测到前台活动时智能让出算力）。被单评测、Matrix、Memory A/B 三个编排共同复用。 |
| `datasets.py` | 数据集文件层：`.myrm/eval_datasets/` 下 JSONL 数据集发现（`get_dataset_path`/`get_all_datasets`）与读写（`get_eval_cases`/`save_eval_cases`），含 legacy `eval_cases.jsonl` 迁移。 |
| `reports.py` | 单评测报告文件层：`.myrm/eval_reports/` 下 `latest.jsonl` 摘要与历史报告读取（`get_latest_report_summary`/`get_all_report_summaries`）。 |
| `executor.py` | 实现了 `LocalEvalExecutor`，适配 Harness 的 `AgentExecutor` 协议。始终以 `unattended_mode=True` 运行（跳过 ask_question_tool 工具注册 + 注入无人值守系统提示词），防止自动化评测被 HITL 交互阻塞。支持接收 `profile_id` 动态覆盖 Agent 属性（含 `ResolvedAgentProfile` 的 builtin tools、`auto_restore_domains`、`memory_decay_profile`）；profile resolve 后（`benchmark_mode` 清空前）经 **`profile_output_suffixes`** 注入 personality + `response_locale_policy` 至 `user_instructions` 尾；并解析 profile/eval/chat 绑定的 Shared Context 注入记忆运行时。支持 `benchmark_mode` 基准模式：清空 system prompt、禁用扩展工具/技能/MCP/子 Agent/共享记忆/Web 搜索，关闭 replan，确保公平基准对比；**`benchmark_tools` 白名单**（由基准注册表声明，如 BrowseComp 的 `("web_search",)`）在 CORE file/shell 基线之上按需注入，修复了「基准模式一刀切禁用全部工具导致 Web 类基准不可跑」的工具面缺陷。捕获 Agent stream 的 TOKEN_USAGE 事件，填充 AgentResponse.token_usage 供报告使用。包含评测工作空间的物理防污染隔离，为每个并发执行的用例动态分配沙箱内的专属独立路径 (`.myrm/eval_workspaces/`) 彻底杜绝测试资源文件竞态冲突。支持 `workspace_seed_map`：外部数据集（如 WorkBuddy Bench）预置的只读任务工作区会在用例执行前拷贝进会话隔离目录。 |
| `matrix.py` | Matrix 评测：`run_matrix_eval_background` 跨配置矩阵评测——同一数据集在多个 AgentProfile 上顺序执行，输出 stable/regression 分类报告；配套 `get_matrix_eval_status`/`abort_matrix_eval`/`get_latest_matrix_report`，报告存 `.myrm/matrix_reports/`。 |
| `memory_ab.py` | **Memory A/B 评测**：`run_memory_ab_background` 复用 `MatrixRunner` 在**任意外部基准**（`benchmark_id`，含 WBBench 子集与 BrowseComp 等注册基准）上并行对比 `enable_memory=True/False` 两种 agent 配置，配合 `LocalEvalExecutor` 的 `memory_base_path` 隔离参数与 `create_memory_manager` 的 `base_path` 注入，将对照组记忆写入会话级临时目录 `.myrm/eval_memory_ab/` 并在结束 `evict_cached_memory_manager` 清理（含释放 harness 嵌入式 Qdrant 单例缓存）后删除，杜绝污染用户真实记忆；报告在 per-profile summary 中追加 `memory_tool_calls`（统计每臂真实调用 `memory_*` 工具的次数，用于区分「记忆未帮助」与「记忆从未被使用」，规避测量衰减）；双臂统一注入基准声明的 `benchmark_tools` 白名单（如 BrowseComp 的 `web_search`）；接受 `limit` 透传给 `build_benchmark_cases` 做抽样；**LLM 判分基准（非 `wb-bench-` 前缀）经 `_resolve_judge_config` 解析用户 model_cfg 注入 `MatrixRunner`，保证双 arm 用同一判分模型**；WBBench（native 确定性判分）跳过 judge 解析避免无谓配置加载。配套 `get_memory_ab_status`/`abort_memory_ab`/`get_latest_memory_ab_report` 支持进度查询、熔断与报告读取，`get_memory_ab_report_history`/`get_memory_ab_report` 支持按时间戳倒序列出历史报告摘要并回看指定报告（报告存 `.myrm/memory_ab_reports/`，损坏文件跳过并告警）。 |
| `service.py` | 单评测编排服务：`run_eval_suite_background`/`run_eval_suite` 异步调度器（支持 `external_cases` 跳过 JSONL 加载、`workspace_seed_map` 透传做工作区预置、`benchmark_mode`、**`benchmark_tools` 白名单透传**）、`run_benchmark_background`/`run_benchmark_download_background` 泛化基准编排（WBBench 子集 + 注册第三方基准统一流程，复用同一 SSE 状态机，`stage`/`stage_subset_id`/`download_progress` 分阶段实时展示进度，`abort_eval` 在下载阶段经 `abort_requested` 联动下载流 `should_abort` 实现可取消下载；`run_benchmark_background` 接受 `limit` 抽样数，经 `build_benchmark_cases` 以固定 seed 从全量用例中抽取子集，控制成本与时长）、`run_wb_bench_background`/`run_wb_bench_download_background` 作为 legacy 兼容入口委托到泛化流程、`_build_eval_manifest` 捕获 profile 模型/引擎参数/tool policy/提示词指纹并记录 `judge_model`（LLM 判分基准所用模型，供前端报告展示）；**judge 配置注入**：`_resolve_judge_config` 从用户 `load_user_configs` 的 `model_cfg` 解析出 `JudgeConfig`（model/api_key/api_base），注入 `EvalRunner`，使 LLM-as-a-Judge 使用用户自配的判分模型与凭据，杜绝默认 `gpt-4o-mini` 导致非 OpenAI 用户判分失败；summary 透出 `avg_pass_rate`（EvalResult 聚合的每轮 test pass rate 均值，供前端赛道卡片区分展示）。 |
| `benchmarks.py` | **外部基准统一目录门面**（业务层）：合并 WBBench 专属适配器（`wb-bench-` 前缀）与框架注册表注册的第三方基准（如 BrowseComp）为单一 catalog，供前端与 eval 服务消费。`list_benchmark_sources` 返回带本地状态与 `benchmark_id`/`provider`/`supports_memory_ab` 的完整卡片数据；`ensure_benchmark_source`/`build_benchmark_cases` 按 `benchmark_id` 分发到对应适配器（下载 / 构建可运行用例 + 工作区种子映射）；**`limit` 抽样**：`build_benchmark_cases` 接受 `limit`，在 `limit>0` 且小于全量时以固定 seed 42 随机抽样（`random.Random(42).sample`）保证可复现，同步裁剪 `workspace_seed_map`（按被抽样 case 的 message 匹配），实现小样本快速验证；`benchmark_required_tools` 解析基准声明的 `required_tools` 白名单供 `benchmark_mode` 注入。 |
| `browse_comp.py` | **BrowseComp 适配器**（OpenAI 网页研究基准）：从官方加密 CSV（`openaipublic.blob.core.windows.net`）下载（SHA256 校验 + 指数退避重试 + 可取消下载），按官方 canary XOR 方案解密 `problem`/`answer` 列，构建 `MultiTurnEvalCase`；判分采用 harness `SemanticAssertion` LLM-as-a-Judge（judge prompt 复刻官方 BrowseComp 评分规则，含括号组互换/矛盾/遗漏判定）；声明 `required_tools=("web_search",)` + `supports_memory_ab=True`，模块导入时经 `register_benchmark` 注册进框架基准注册表。 |
| `wb_bench.py` | WorkBuddy Bench 外部基准数据集适配器（数据源层）：提供四个赛道（Code/Web/Office/Security）的目录清单（含本地下载状态与评分模式），从 HuggingFace 下载归档（SHA256 校验 + 原子解压 + 指数退避重试 + 下载进度回调 + 可取消下载 `should_abort`/`DownloadAbortedError` + 离线降级复用），`build_wb_bench_cases` 自 `wb_bench_workspace` 透出（保持既有调用方与测试的命名空间稳定）。 |
| `wb_bench_workspace.py` | WorkBuddy Bench 任务构建与工作区预置层：迭代源目录任务，将 `instruction.md` 映射为 `MultiTurnEvalCase`，解包 `workspace.tar.gz` 预置任务工作区（剥离单一顶层目录并保留 symlink + `.ready` 幂等标记）；非 Web 赛道逐任务经 `wb_bench_verifier` 注入 `test_suite` Rule 断言；Web 赛道仅将评分模式写入 case 元数据；构建期逐任务预置工作区循环响应 `should_abort` 中止。 |
| `wb_bench_verifier.py` | WorkBuddy Bench 判分断言构建层：解析任务自带官方判分协议（Code/Security 的 `tests/verifier.toml` 三家族 `script_verifier` 跑 `verifier.py`、`pytest_injected` 注入测试并执行完整 `[run] command`（pytest 或自定义 runner 如 Django `runtests.py`）、`repo_understanding` 跑 `scorer.py`；Office 无 `family` 键的 `schema_version=workbuddy.office.verifier.v1` 经 `[run] command`/`[env]` 重写 Harbor 路径并显式注入 `PYTHONPATH={workspace}`（剥离 Harbor 内联 `${PYTHONPATH:-}` 前缀，规避沙箱 `${}` 命令拦截）；Security 直写判分 `tests/scoring.py`/`test_outputs.py` 写 `reward.json`）。判分资产留在源缓存，经 `SandboxAssertion.readonly_paths` 只读挂载，`{workspace}` 占位符指向 agent 实时工作区，`gold.patch` 永不进入 agent 工作区杜绝污染；断言统一 `timeout=600` 对齐 WBBench verifier 默认值，pytest 判分前清理旧 JUnit 报告，JUnit/奖励结果写入 `result_file`。实现无需 LLM 的确定性判分。 |
| `capture.py` | 从主聊天界面“一键淬炼”为评测用例 (GUI Flywheel)。基于真实对话记录，抽取 `messages` 和完整的结构化 Tool Arguments 并生成标准 `EvalCase` 测试集，可绑定指定的 `dataset_id`，打通日常开发测试与评估的闭环飞轮。 |

## 依赖关系

- **内部依赖**：
  - `myrm_agent_harness.eval`：提供核心的评估引擎、断言协议（`SemanticAssertion` 等）、报告器，以及基准注册表（`register_benchmark`/`list_benchmarks`/`get_benchmark`）。
  - `app.ai_agents.agents.AgentFactory`：用于实例化真实的业务 Agent。
  - `app.core.sandbox.local_executor.LocalExecutor`：提供沙箱环境的命令执行和文件读写能力。
  - `app.services.memory.shared_context`：提供评测运行时 Shared Context 绑定解析。
- **被依赖**：
  - `app.api.eval.router`：API 层调用本模块的服务（单评测 + WBBench）。
  - `app.api.eval.benchmarks_router`：外部基准统一 HTTP 层（`/eval/benchmarks` + legacy `/eval/wb-bench`），调用 `app.core.eval.benchmarks` 与 `app.core.eval.service`。
  - `app.api.eval.matrix_router` / `app.api.eval.memory_ab_router`：分别调用 `app.core.eval.matrix` / `app.core.eval.memory_ab`。
