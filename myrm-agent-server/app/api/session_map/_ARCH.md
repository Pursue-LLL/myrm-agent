# session_map/

## 架构概述

“项目维度可视化会话地图与 Agent 状态全景驾驶舱”后端 API 模块：
将分散的聊天会话（Chat）按项目（Project）聚类：每个项目一个容器，携带项目自身的工作路径（`workspace_path`，项目未设置时为空）；未归属任何项目的会话归入 `Global Workspace` 容器（有会话时才出现）。实时汇聚多 Agent 运行状态（working/ready/waiting_input/error/idle），提供 Fleet 级聚合指标与跨会话关键词检索能力。

所有数字都来自已存储的行与网关的实时状态；数据库故障以错误响应暴露，不返回占位数据。地图只绘制最近更新的 200 个会话。

## 文件清单

| 文件 | 职责 |
| ---- | ---- |
| `models.py` | Pydantic 数据契约：`SessionNodeModel`、`ProjectClusterModel`、`FleetCockpitSummary`、`SessionSearchRequest/Response` |
| `routes.py` | API 端点实现：`GET /projects`（项目拓扑图谱）、`GET /cockpit`（驾驶舱大盘，与 `/projects` 共用同一份会话节点聚合）、`POST /search`（跨会话全文检索）。会话状态按优先级判定：`error`（压缩连续失败 >3 次）> `waiting_input`（该 chat 有挂起 Agent 的待决审批：`ApprovalRecord` 为 PENDING 且不是后台 growth draft，口径同 `ApprovalRegistry.count_pending_for_chat`）> `working`（`AgentGateway.active_session_ids()` 含该 chat，即有回合在执行）> `idle`（已压缩）> `ready` |
| `__init__.py` | 包门面：统一导出 `router` |
| `_ARCH.md` | 本文档：模块架构说明与契约索引 |

## 依赖

- FastAPI / Pydantic v2
- SQLAlchemy 异步 ORM 查询（`Project`、`Chat`、`ApprovalRecord`）
- `services/agent/gateway.py`：`AgentGateway.active_session_ids()`（正在执行回合的 chat 集合）
- `services/skills/growth/constants.py`：`is_background_growth_approval`（后台 growth draft 分流的唯一判据）

## 用户入口

- 前端 `SessionMapGraph.tsx` 2D 拓扑会话地图
- 前端 `AgentFleetCockpit.tsx` 状态全景驾驶舱
- 前端 `SessionContextJumpModal.tsx` 一键现场跳回
