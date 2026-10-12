# System Assistant API Module

## 架构定位

本模块为系统级自然语言控制中枢（小莫助手）的后端服务接口层。负责接收用户口语化自然语言指令，解析系统管理意图（如创建项目、查询任务、终止后台会话、系统健康自检），代劳执行相关操作并返回结构化执行卡片与后继建议动作。

## 模块清单

| 文件 | 职责 | 规范要求 |
|---|---|---|
| `routes.py` | 暴露 `POST /api/v1/system-assistant/command` 与 `GET /api/v1/system-assistant/status` | `< 180` 行，强类型 Pydantic 模型，无 `Any` |
| `__init__.py` | 统一导出门面路由 | 标准包导出 |
| `_ARCH.md` | 本目录架构与文件索引 | 遵循架构规范 |

## 意图分类与代劳机制

- `create_project`：自动生成项目 ID，绑定沙箱实例与 Git 状态；
- `query_tasks`：汇总当前运行中的 Agent 任务及状态指标；
- `terminate_tasks`：批量终止并释放后台会话与沙箱进程；
- `system_status`：诊断系统资源负载、CPU、内存与健康评分；
- `general_query`：通用答疑并给出高频操作建议引导。
