# app/config/settings 子包架构

应用配置（pydantic-settings）。`AppSettings` 由各组配置组合而成，`settings` 为进程级单例。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `AppSettings`、`settings`、`get_settings` 与全部配置组 | — |
| `llm.py` | 核心 | `LLMProvider`、`ProviderCacheConfig` / `PROVIDER_CACHE_CONFIGS`、`CacheSettings` | ✅ |
| `channels.py` | 核心 | DingTalk / MCP / BrowserPool / WebUI 配置组 | ✅ |
| `security.py` | 核心 | Bash 审计、代码执行、安全、Agent Gateway 配置组 | ✅ |
| `infra.py` | 核心 | 数据库、服务、控制面、监控、上下文压缩与记忆遥测、执行缓存配置组 | ✅ |
| `app.py` | 核心 | `AppSettings` 组合体与 env / dotenv 源 | ✅ |
| `singleton.py` | 核心 | `get_settings()`（`lru_cache` 单例）与模块级 `settings` | ✅ |

## 依赖关系

- 上游：`pydantic` / `pydantic-settings`、`app.config.deploy_mode`、`app.config.paths`
- 下游：全仓 212 个模块通过 `from app.config.settings import settings / get_settings` 读取配置
