# app/core/channel_bridge/topic_config 子包架构

渠道 Topic 配置域。`SqlTopicManager` 由四个 mixin 组合而成，每个 mixin 负责一类操作；共享常量与 helper 在 `common.py`。`app.core.channel_bridge.topic_config` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `SqlTopicManager`、`_CHANNEL_LEVEL_KEY` 与 search-bind 错误 helper | — |
| `common.py` | 辅助 | 共享常量（缓存 TTL、默认空闲超时、`_UNSET`、消息文案）、logger、`clean_identity_id` / `is_search_agent_channel_bind_error` | ✅ |
| `manager.py` | 核心 | `SqlTopicManager(BindingMixin, IdentityMixin, PolicyMixin, ConfigStoreMixin)` + `__init__`（缓存与默认超时） | ✅ |
| `binding.py` | 核心 | `resolve_topic` / `bind_topic` / `unbind_topic` / `sync_topic_metadata`：解析、绑定（拒绝 search agent、workspace 互斥）、解绑与元数据同步 | ✅ |
| `identity.py` | 核心 | 身份撤销/恢复、过期判定、活跃时间刷新、从全部绑定中移除 Agent | ✅ |
| `policy.py` | 核心 | 读路径、Agent ID 解析、绑定键删除、渠道可绑定性校验与 search-track 判定 | ✅ |
| `config_store.py` | 核心 | UserConfig 中 topic map 的读写与进程内缓存失效 | ✅ |

## 依赖关系

- 上游：`app.channels.types`（`TopicContext` / `IdentityScopeMode` / `ReplyMode` …）、`app.channels.types.thread_sharing`
- 下游：`app/core/channel_bridge/setup.py`、`app/api/channels/topics.py`、`app/core/cron/adapters/*`
