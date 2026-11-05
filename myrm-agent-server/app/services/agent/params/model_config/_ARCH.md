# app/services/agent/params/model_config 子包架构

模型配置子域：把一个不含密钥的 `ModelSelection` 解析成可调用模型的 `ModelConfig`，以及解析它需要的 provider 行与 API Key。所有入口（Web / Channel / Cron / Voice / Eval）共用这一份解析逻辑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合导出 `_resolve_model_config` 与 provider 查找/规范化 API | — |
| `resolvers.py` | 核心 | `_resolve_model_config()`：ModelSelection → ModelConfig；API Key 来自 WebUI provider 行，多 Key 走 credential pool；base URL 来自 selection 或 provider 行 | ✅ |
| `providers.py` | 辅助 | providerId 规范化、行匹配、密钥查找；**仅** WebUI providers，无 env 回退；显式加载 `shared/config/provider_legacy_remap.json`（monorepo / Docker `/shared` / PyInstaller bundle / `MYRM_SHARED_CONFIG_ROOT`） | ✅ |

## 依赖关系

- 上游：`params/models.py`（`ModelSelection`）、`app.core.types`（`ModelConfig`）、`app.core.wire`（模型配置补全）
- 下游：`app.core.channel_bridge.model_resolver`（默认模型 / provider 解析）
- 外部调用方：`app/api/agents/general_agent/media_config.py`、`app/services/chat/chat_compaction.py`、`app/services/memory/extract_retry/`、评测与迁移入口
