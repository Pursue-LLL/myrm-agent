# datasets/ 模块架构

## 架构概述

数据集导出 HTTP 入口层。将事件日志轨迹数据导出为标准微调格式（ShareGPT / Alpaca / OpenAI JSONL），支持 PII 脱敏、质量过滤和增量导出。上级：[../_ARCH.md](../_ARCH.md)。

## 文件

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包导出 router | — |
| `router.py` | 核心 | REST API 端点（export/formats/files/download） | ✅ |

## 端点

| 方法 | 路径 | 职责 |
|------|------|------|
| GET | `/formats` | 列出可用导出格式 |
| POST | `/export` | 触发数据集导出 |
| GET | `/files` | 列出已导出文件 |
| GET | `/files/{filename}` | 下载导出文件 |

## 依赖

- `myrm_agent_harness.agent.event_log.dataset_export`: 全部导出逻辑
- `myrm_agent_harness.agent.event_log.backends.file_backend`: 事件日志后端

## 约束

- 仅 HTTP 薄层，禁止在此写业务逻辑
- 导出操作为同步阻塞（读文件 + 写文件），适合中小规模日志
