# artifacts 模块架构


---

## 架构概述

业务层工件系统，采用回调注入设计（V4）。框架层发出 `artifacts_ready` 事件，业务层通过 `on_artifacts_ready` 回调按需读取、持久化并生成最终 `artifacts` 事件。默认关闭、懒加载、零样板代码。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|-----|------|------|-------|
| `processor.py` | 核心 | 模板方法：`LocalArtifactProcessor` / `ArtifactProcessor`；SSE `file_id` 与 DB 同步 | ✅ |
| `listener.py` | 核心 | `upsert_processor_artifact`（id=file_id）、`ensure_artifact_for_deploy` JIT | ✅ |
| `__init__.py` | 核心 | 模块入口，公共 API 导出 | ⚠️ 待补 |

---

## 依赖关系

- **内部**：`app.platform`（`get_artifact_processor`）、`app.config.config`（API_PREFIX）
- **外部**：`myrm_agent_harness.agent`（`create_skill_agent`、`collect_artifacts`）、S3/Files 服务（Sandbox）、本地路径（Local）
