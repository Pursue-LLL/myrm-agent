# services/memory/codebase_diff 模块架构

## 架构概述

代码库记忆大 Diff 分级降级与拓扑摘要业务服务适配层：包装 harness `CodebaseDiffFallbackSuite`，将底层领域模型（`DiffVolumeTier`、`DiffCategory`、`DiffFileEntry`、`DirectoryAggregate`、`DiffFallbackVerdict`）转换为 Server API DTO，并维护单进程单例 provider。核心算法与执行逻辑全部在 harness 引擎，本目录仅负责 DTO 适配与单例状态管理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `provider.py` | 核心 | `CodebaseDiffProvider`：持有 harness suite，执行 numstat 解析、四层漏斗评估、截断防护及 DTO 转换 | — |
| `__init__.py` | 入口 | 导出 `CodebaseDiffProvider` 与单例获取函数 `get_codebase_diff_provider` | — |

## 模块依赖

- 上游：`myrm_agent_harness.toolkits.memory.codebase_diff_fallback`（执行引擎）、`app.schemas.codebase_diff`（API DTO）
- 下游：`app/api/memory/codebase_diff_router.py`
