# app/api/kanban/schemas 子包架构

Kanban API 的请求/响应模型。按 API 区域分模块，`__init__.py` 统一 re-export，路由与 SDK 只依赖这一个导入路径。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 re-export 全部 69 个模型（`from app.api.kanban.schemas import X` 保持不变） | — |
| `boards.py` | 核心 | 看板创建/更新/响应、按 Agent 的任务分布与汇总 | ✅ |
| `tasks.py` | 核心 | 任务创建/更新/移动、提升、回收、评审（approve/reject）与批量生命周期请求体 | ✅ |
| `diagnostics.py` | 核心 | 诊断规则命中与嵌入 `TaskResponse` 的摘要 | ✅ |
| `task_responses.py` | 核心 | 任务/回收、运行、事件、看板事件的响应模型 | ✅ |
| `links.py` | 核心 | 评论、依赖边与边列表 | ✅ |
| `spec.py` | 核心 | Specifier 结果与 apply-spec 请求体 | ✅ |
| `decompose.py` | 核心 | 拆分预览的子任务提案与 apply-decompose 请求体 | ✅ |
| `pipeline.py` | 核心 | 流水线模板：发现问卷、任务图变体、模板列表/详情、实例化与估算 | ✅ |
| `planning.py` | 核心 | DAG 计划修订的请求/响应 | ✅ |
| `race.py` | 核心 | Race 启动/估算/裁决请求体与 lane 对比响应 | ✅ |

## 依赖关系

- 上游：`pydantic`（BaseModel / Field）
- 下游：`app/api/kanban/*` 路由、`app/services/kanban/*`（构造响应）、`app/core/kanban/*`（枚举与类型）
