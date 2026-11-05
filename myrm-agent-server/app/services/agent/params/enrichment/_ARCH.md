# app/services/agent/params/enrichment 子包架构

用户消息富化域。把原始 query 变成最终发给模型的那一份：@ 引用、上传文件、归档恢复动作、@专家指令、/learn 重写、超长文本溢出。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合导出 `enrich_query` 与 archive restore / upload sync 的公共 API | — |
| `pipeline.py` | 核心 | `enrich_query()`：按固定顺序注入 archive restore、@mention、上传文件、@agent 委派、/learn 重写，最后过 ContextBomb 溢出；`EnrichedQuery` 返回最终 query + 告警 + restore 结果 + JIT 子 Agent | ✅ |
| `archive_restore.py` | 核心 | Typed archive restore 校验与 prompt 物化（`prevalidate_archive_restore_actions`、XML 注入） | ✅ |
| `upload_sync.py` | 辅助 | 上传文件 workspace 同步与 RAG 智能路由：>100KB 复制到 `{workspace}/_uploaded/`，大型文档标记 `wiki_ingest_then_query` | ✅ |

## 依赖关系

- 上游：`params/converter.py`（唯一调用方）、`params/mention/`（引用展开）、`params/conversion/chat_context.py`（workspace 与共享库）
- 下游：`app.services.chat.context_bomb_guard`、`app.core.channel_bridge.learn_handler`、`app.services.agent.agent_service`（@专家）
