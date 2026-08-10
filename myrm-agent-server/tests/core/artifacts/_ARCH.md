# tests/core/artifacts 模块架构

---

## 架构概述

工件核心链路回归测试。覆盖 chat processor `file_id` 与 DB `Artifact.id` 对齐、upsert-emit 一致性、oversized shareable IM deliverable 路径，以及 publish API 按同一 id 查找。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `conftest.py` | 辅助 | autouse mock `upsert_processor_artifact`（SSOT；api/artifacts 经 pytest_plugins 复用） |
| `test_artifact_file_id_chain.py` | 核心 | `upsert_processor_artifact` → `ensure_artifact_for_deploy` → `POST /{file_id}/publish` 全链路 |
| `test_listener.py` | 核心 | `resolve_sandbox_file_path` 与 artifact 事件持久化 |
| `test_processor_oversized_shareable.py` | 核心 | Local reference-only persist、sandboxes 路径、processor→deliverable 集成 |
| `test_processor_short_file_id.py` | 模块 | `short_file_id` 透传 → artifacts SSE JSON |
| `test_processor_upsert_emit.py` | 模块 | upsert 失败不 emit；部分 upsert 失败只 emit 成功项 |

---

## 依赖关系

- `app.core.artifacts.listener`
- `app.core.artifacts.processor`
- `app.api.files.hosting_api`
