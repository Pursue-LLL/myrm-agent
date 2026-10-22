# workspace/promotion/

## 架构概述

便签（Scratchpad）升格为正式工作区项目的服务层实现。
调用底层 Harness `ScratchpadPromotionEngine` 编译项目种子（包含血缘原稿 `docs/scratchpad_origin.md` 与 `README.md`），在沙箱/本地文件系统中安全落盘，并生成不可降解的初始上下文注入提示词。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `ProjectPromotionService` 与 `PromotedProjectResult` | — |
| `service.py` | 核心 | 驱动便签草稿编译、目录防穿越校验与文件物理落盘 | ✅ |
| `_ARCH.md` | 架构 | 模块架构说明与文件索引 | — |

## 依赖关系

### 内部依赖
- `myrm_agent_harness.agent.context_management.scratchpad_promotion` — Harness 框架层种子编译引擎

### 被依赖方
- `app/api/workspace/promotion_router.py` — POST `/api/v1/workspace/promote` 升格 HTTP 端点
