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
| `executor.py` | 实现了 `LocalEvalExecutor`，适配 Harness 的 `AgentExecutor` 协议。始终以 `unattended_mode=True` 运行（跳过 ask_question_tool 工具注册 + 注入无人值守系统提示词），防止自动化评测被 HITL 交互阻塞。支持接收 `profile_id` 动态覆盖 Agent 属性（含 `ResolvedAgentProfile` 的 builtin tools、`auto_restore_domains`、`memory_decay_profile`）；profile resolve 后（`benchmark_mode` 清空前）经 **`profile_output_suffixes`** 注入 personality + `response_locale_policy` 至 `user_instructions` 尾；并解析 profile/eval/chat 绑定的 Shared Context 注入记忆运行时。支持 `benchmark_mode` 基准模式：清空 system prompt、禁用扩展工具/技能/MCP/子 Agent/共享记忆/Web 搜索，关闭 replan，确保公平基准对比。捕获 Agent stream 的 TOKEN_USAGE 事件，填充 AgentResponse.token_usage 供报告使用。包含评测工作空间的物理防污染隔离，为每个并发执行的用例动态分配沙箱内的专属独立路径 (`.myrm/eval_workspaces/`) 彻底杜绝测试资源文件竞态冲突。支持 `workspace_seed_map`：外部数据集（如 WorkBuddy Bench）预置的只读任务工作区会在用例执行前拷贝进会话隔离目录。 |
| `matrix.py` | Matrix 评测：`run_matrix_eval_background` 跨配置矩阵评测——同一数据集在多个 AgentProfile 上顺序执行，输出 stable/regression 分类报告；配套 `get_matrix_eval_status`/`abort_matrix_eval`/`get_latest_matrix_report`，报告存 `.myrm/matrix_reports/`。 |
| `memory_ab.py` | **Memory A/B 评测**：`run_memory_ab_background` 复用 `MatrixRunner` 在同一 WBBench 数据集上并行对比 `enable_memory=True/False` 两种 agent 配置，配合 `LocalEvalExecutor` 的 `memory_base_path` 隔离参数与 `create_memory_manager` 的 `base_path` 注入，将对照组记忆写入会话级临时目录 `.myrm/eval_memory_ab/` 并在结束 `evict_cached_memory_manager` 清理后删除，杜绝污染用户真实记忆；报告在 per-profile summary 中追加 `memory_tool_calls`（统计每臂真实调用 `memory_*` 工具的次数，用于区分「记忆未帮助」与「记忆从未被使用」，规避测量衰减）；配套 `get_memory_ab_status`/`abort_memory_ab`/`get_latest_memory_ab_report` 支持进度查询、熔断与报告读取，`get_memory_ab_report_history`/`get_memory_ab_report` 支持按时间戳倒序列出历史报告摘要并回看指定报告（报告存 `.myrm/memory_ab_reports/`，损坏文件跳过并告警）。 |
| `service.py` | 单评测编排服务：`run_eval_suite_background`/`run_eval_suite` 异步调度器（支持 `external_cases` 跳过 JSONL 加载、`workspace_seed_map` 透传做工作区预置、`benchmark_mode`）、`run_wb_bench_background`/`run_wb_bench_download_background` 编排 WorkBuddy Bench 子集从下载到执行的完整后台流程（复用同一 SSE 状态机，`stage`/`stage_subset_id`/`download_progress` 分阶段实时展示进度，`abort_eval` 在下载阶段经 `abort_requested` 联动下载流 `should_abort` 实现可取消下载）、`_build_eval_manifest` 捕获 profile 模型/引擎参数/tool policy/提示词指纹；summary 透出 `avg_pass_rate`（EvalResult 聚合的每轮 test pass rate 均值，供前端赛道卡片区分展示）。 |
| `wb_bench.py` | WorkBuddy Bench 外部基准数据集适配器（数据源层）：提供四个赛道（Code/Web/Office/Security）的目录清单（含本地下载状态与评分模式），从 HuggingFace 下载归档（SHA256 校验 + 原子解压 + 指数退避重试 + 下载进度回调 + 可取消下载 `should_abort`/`DownloadAbortedError` + 离线降级复用），`build_wb_bench_cases` 自 `wb_bench_workspace` 透出（保持既有调用方与测试的命名空间稳定）。 |
| `wb_bench_workspace.py` | WorkBuddy Bench 任务构建与工作区预置层：迭代源目录任务，将 `instruction.md` 映射为 `MultiTurnEvalCase`，解包 `workspace.tar.gz` 预置只读任务工作区（剥离单一顶层目录并保留 symlink + `.ready` 幂等标记）。评分策略按赛道差异化：Code/Office/Security 赛道将任务自带 `tests/` 镜像到工作区 `.wb_bench/tests`（隐藏目录避免污染 agent 工作区），并注入 `test_suite` Rule 断言（Code/Office 跑 pytest 解析 JUnit XML、Security 跑任务自带 scorer；断言统一配置 `timeout=600` 对齐 WBBench `[verifier] timeout_sec`，JUnit/奖励结果写入 `result_file`），实现无需 LLM 的确定性判分；Web 赛道依赖 VLM 判定，注入断言留空，仅将评分模式写入 case 元数据。构建期逐任务预置工作区循环响应 `should_abort` 中止。 |
| `capture.py` | 从主聊天界面“一键淬炼”为评测用例 (GUI Flywheel)。基于真实对话记录，抽取 `messages` 和完整的结构化 Tool Arguments 并生成标准 `EvalCase` 测试集，可绑定指定的 `dataset_id`，打通日常开发测试与评估的闭环飞轮。 |

## 依赖关系

- **内部依赖**：
  - `myrm_agent_harness.eval`：提供核心的评估引擎、断言协议和报告器。
  - `app.ai_agents.agents.AgentFactory`：用于实例化真实的业务 Agent。
  - `app.core.sandbox.local_executor.LocalExecutor`：提供沙箱环境的命令执行和文件读写能力。
  - `app.services.memory.shared_context`：提供评测运行时 Shared Context 绑定解析。
- **被依赖**：
  - `app.api.eval.router`：API 层调用本模块的服务（单评测 + WBBench）。
  - `app.api.eval.matrix_router` / `app.api.eval.memory_ab_router`：分别调用 `app.core.eval.matrix` / `app.core.eval.memory_ab`。
