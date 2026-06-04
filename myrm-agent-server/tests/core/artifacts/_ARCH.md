# tests/core/artifacts 模块架构

---

## 架构概述

工件核心链路回归测试。覆盖 chat processor `file_id` 与 DB `Artifact.id` 对齐，以及 deploy API 按同一 id 查找。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_artifact_file_id_chain.py` | 核心 | `upsert_processor_artifact` → `ensure_artifact_for_deploy` → `POST /{file_id}/deploy` 全链路 |

---

## 依赖关系

- `app.core.artifacts.listener`
- `app.api.files.deploy_api`
