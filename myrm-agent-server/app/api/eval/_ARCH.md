# app/api/eval 模块架构


---

## 架构概述

`eval` 模块是 Myrm Agent Server 提供的 Agent 评估与回归测试 API。它作为 `myrm_agent_harness/eval` 核心引擎的业务层包装，负责在单机沙箱环境中调度、执行和持久化测试用例与报告。

## 核心设计原则

1. **单机沙箱策略**：测试用例（`eval_cases.jsonl`）和测试报告（`eval_reports/`）均持久化在用户专属的 `.myrm/` 目录下，不使用中心化数据库，确保数据私有和架构轻量。
2. **异步执行**：由于 Agent 评估可能耗时较长，采用 FastAPI 的 `BackgroundTasks` 进行异步调度，前端通过轮询 `/status` 接口获取实时进度。
3. **引擎解耦**：通过 `app/core/eval/executor.py` 中的 `LocalEvalExecutor` 桥接了 Harness 的 `AgentExecutor` 协议和 Server 的 `AgentFactory`，实现了框架层与业务层的完美解耦。

## 文件清单

| 文件 | 职责 |
|------|------|
| `router.py` | 注册所有与 Eval 相关的 HTTP 端点 |

## 路由端点

| 方法 | 路径 | 职责 |
|------|------|------|
| `POST` | `/run` | 触发后台异步评估任务 (支持指定 profile_id) |
| `POST` | `/abort` | 强制安全中断正在运行的后台评估任务 |
| `GET` | `/stream` | 通过 SSE 实时推送评估进度和状态 |
| `GET` | `/status` | 轮询当前评估任务的进度和状态 |
| `GET` | `/reports` | 获取所有历史评估报告的汇总列表 |
| `GET` | `/reports/latest` | 获取最新一次评估的汇总报告 |
| `GET` | `/reports/{filename}` | 获取特定历史评估报告的完整明细 |
| `GET` | `/datasets` | 获取当前可用的评测数据集列表 |
| `GET` | `/datasets/{dataset_id}` | 获取特定评测数据集的内容 |
| `PUT` | `/datasets/{dataset_id}` | 更新/保存特定评测数据集的内容 |
| `POST` | `/cases/from-chat/{chat_id}` | (支持 `dataset_id` Query参数) 从主聊天界面一键淬炼飞轮，捕获并生成结构化测试用例 |
| `GET` | `/cases` | (向后兼容) 读取默认数据集的测试用例 |
| `PUT` | `/cases` | (向后兼容) 更新默认数据集的测试用例 |
| `GET` | `/internal/metrics/eval` | （内部接口）供 Control Plane 拉取评估指标数据 |

## 依赖关系

- 依赖 `myrm_agent_harness.eval` 提供核心断言和执行引擎。
- 依赖 `app.core.eval.service` 提供具体的业务逻辑（如文件读写、后台任务状态管理）。