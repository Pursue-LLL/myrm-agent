# tests/core/artifacts 模块架构

---

## 架构概述

工件核心链路回归测试。覆盖 chat processor `file_id` 与 DB `Artifact.id` 对齐、upsert-emit 一致性、oversized shareable IM deliverable 路径，以及 publish API 按同一 id 查找。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_artifact_file_id_chain.py` | 核心 | `upsert_processor_artifact` → `ensure_artifact_for_deploy` → `POST /{file_id}/publish` 全链路 |
| `test_listener.py` | 核心 | `resolve_sandbox_file_path` 与 artifact 事件持久化 |
| `test_artifact_identity.py` | 核心 | 一个文件一条工件：同一文件的处理得到同一个 id、再次登记追加版本不增行、并发登记输掉插入的一方并入已有行（含 4 个会话并发）；处理文件时登记相对工作区的路径，登记带路径时写入、不带路径时保持原值、带了新路径时替换 |
| `test_source_path.py` | 核心 | `Artifact.source_path` 的编码：工作区内存相对路径、工作区外存绝对路径、同一文件的各种写法得到同一个值、能还原出原路径 |
| `test_processor_oversized_shareable.py` | 核心 | Local reference-only persist、sandboxes 路径、processor→deliverable 集成 |
| `test_processor_short_file_id.py` | 模块 | `short_file_id` 透传 → artifacts SSE JSON |
| `test_processor_upsert_emit.py` | 模块 | upsert 失败不 emit；部分 upsert 失败只 emit 成功项 |

---

## 依赖关系

- `app.core.artifacts.listener`
- `app.core.artifacts.processor`
- `app.core.artifacts.source_path`
- `app.api.files.hosting_api`
