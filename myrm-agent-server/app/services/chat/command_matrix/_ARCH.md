# command_matrix/

## 架构概述

服务端系统指令矩阵与情境感知推荐服务子包（Item 38 P0）。
收敛全量 5 大能力域（并发协作、数据与科学、安全与凭证、记忆与知识、办公与交付）共 20+ 项高阶指令规范与元数据，
并提供关键词模糊搜索与基于会话运行态（步骤数/耗时/活跃工具/已掌握指令）的情境推荐服务。
上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出门面 `CommandMatrixService` 与 `SYSTEM_COMMAND_MATRIX` | ✅ |
| `registry.py` | 规范 | `SYSTEM_COMMAND_MATRIX` 权威指令全景元数据注册表（包含快捷键、中英文描述、分类、标签与模板） | ✅ |
| `service.py` | 核心 | `CommandMatrixService` 单例业务服务，提供分类过滤、全字段模糊搜索与对接 Harness 引擎的智能推荐 | ✅ |

## 依赖

- `myrm_agent_harness.agent.context_management.capability_matrix` — Harness 框架层推荐推断引擎与契约
