# progression 模块架构

---

## 架构概述

用户能力进度服务。追踪里程碑完成情况，计算用户等级（L1–L5），并在升级时联动 Feature Gate。
使用 UserConfig（config_key='user_progression'）零迁移持久化。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `schema.py` | 核心 | 里程碑定义、等级阈值、Pydantic 模型 | ✅ |
| `service.py` | 核心 | 进度 CRUD（get/mark/compute） | ✅ |
| `gate_sync.py` | 辅助 | 等级变化时自动启用对应 Feature Gate | ✅ |
| `__init__.py` | 入口 | 模块公共 API 导出 | — |

---

## 依赖

### 内部依赖
- `app.services.config.service` — ConfigService 持久化层
- `app.services.features.feature_config_service` — Feature override 持久化
- `myrm_agent_harness.core.features` — Feature registry 和 init

### 被依赖方
- `app.api.progression.router` — HTTP API 端点
- 前端被动触发：`src/lib/progression/tryMarkMilestone.ts`
- 前端触发点：`completionEvents.ts`（first_chat / first_tool_use）、`useToolApprovalResolve.ts`（first_approval）
