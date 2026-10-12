# session_map/

## 架构概述

“项目维度可视化会话地图与 Agent 状态全景驾驶舱”后端 API 模块：
对标 Mobius Agent OS 实践，将分散的聊天会话（Chat）与 Agent 实例按项目（Project）物理容器进行拓扑聚类，绑定独立 Git 仓库与工作路径；实时汇聚多 Agent 运行状态脉冲（working/ready/waiting_input/error/idle），提供 Fleet 级全景驾驶舱聚合指标与跨会话关键词一键检索能力。

## 文件清单

| 文件 | 职责 |
| ---- | ---- |
| `models.py` | Pydantic 数据契约：`SessionNodeModel`、`ProjectClusterModel`、`FleetCockpitSummary`、`SessionSearchRequest/Response` |
| `routes.py` | API 端点实现：`GET /projects`（项目拓扑图谱）、`GET /cockpit`（驾驶舱大盘）、`POST /search`（跨会话全文检索） |
| `__init__.py` | 包门面：统一导出 `router` |
| `_ARCH.md` | 本文档：模块架构说明与契约索引 |

## 依赖

- FastAPI / Pydantic v2
- SQLAlchemy 异步 ORM 查询与沙箱状态容错降级

## 用户入口

- 前端 `SessionMapGraph.tsx` 2D 拓扑会话地图
- 前端 `AgentFleetCockpit.tsx` 状态全景驾驶舱
- 前端 `SessionContextJumpModal.tsx` 一键现场跳回
