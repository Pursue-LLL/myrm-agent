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
| `executor.py` | 实现了 `LocalEvalExecutor`，适配 Harness 的 `AgentExecutor` 协议。始终以 `unattended_mode=True` 运行（跳过 ask_question_tool 工具注册 + 注入无人值守系统提示词），防止自动化评测被 HITL 交互阻塞。支持接收 `profile_id` 动态覆盖 Agent 属性（含 `ResolvedAgentProfile` 的 builtin tools、`auto_restore_domains`、`memory_decay_profile`），并解析 profile/eval/chat 绑定的 Shared Context 注入记忆运行时。捕获 Agent stream 的 TOKEN_USAGE 事件，填充 AgentResponse.token_usage 供报告使用。包含评测工作空间的物理防污染隔离，为每个并发执行的用例动态分配沙箱内的专属独立路径 (`.myrm/eval_workspaces/`) 彻底杜绝测试资源文件竞态冲突。 |
| `service.py` | 评估服务层，提供 `run_eval_suite_background` 异步调度器，以及任务安全熔断 (`abort_eval`)、A/B历史报告读写、数据集隔离管理(`dataset_id`)、支持兼容多轮与单轮用例 (`run_multi_turn`)、SSE进度流生成。包含 `AdaptiveEvalManager` 以根据前台活动智能让出算力。 |
| `capture.py` | 从主聊天界面“一键淬炼”为评测用例 (GUI Flywheel)。基于真实对话记录，抽取 `messages` 和完整的结构化 Tool Arguments 并生成标准 `EvalCase` 测试集，可绑定指定的 `dataset_id`，打通日常开发测试与评估的闭环飞轮。 |

## 依赖关系

- **内部依赖**：
  - `myrm_agent_harness.eval`：提供核心的评估引擎、断言协议和报告器。
  - `app.ai_agents.agents.AgentFactory`：用于实例化真实的业务 Agent。
  - `app.core.sandbox.local_executor.LocalExecutor`：提供沙箱环境的命令执行和文件读写能力。
  - `app.services.memory.shared_context`：提供评测运行时 Shared Context 绑定解析。
- **被依赖**：
  - `app.api.eval.router`：API 层调用本模块的服务。
