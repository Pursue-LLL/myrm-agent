# services/faq — Channel FAQ 语义缓存

## 架构概述

Per-agent FAQ 语义缓存服务。在 IM 渠道消息到达 Agent 执行管线之前，通过向量相似度匹配预配置的 Q&A 对，实现零 LLM 调用的即时回复。

## 数据流

```
InboundMessage → ChannelAgentExecutor.execute_stream
                 ↓ (topic_context.agent_id 存在且非 resume)
                 FaqInterceptor.try_match
                 ↓ (embedding → Qdrant search → score + gap 双校验)
                 命中 → 直接 yield OutboundMessage，跳过 Agent
                 未命中 → 继续正常 Agent 执行
```

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 包入口，re-export 公共 API |
| `corpus.py` | FAQ 语料 CRUD + Qdrant 索引重建（先算完全部向量再动索引：嵌入调用失败时在用的索引原样保留，向量大小取自提供方的应答） |
| `interceptor.py` | 零 LLM 语义拦截器（embedding + 双校验） |
| `tracker.py` | 命中/未命中日志记录 + 分析统计 |
| `factory.py` | FaqInterceptor 工厂：embedding 来自 WebUI retrieval 配置，拦截器按配置（模型/密钥/地址）缓存，配置一变即重建 |

## 依赖关系

- `corpus.py` → `app.database.models.faq`, `myrm_agent_harness.toolkits.vector.base`, `myrm_agent_harness.toolkits.retriever.embedding.base`
- `interceptor.py` → `corpus.py`, 同上 harness 组件
- `tracker.py` → `app.database.models.faq.FaqHitLog`
- `factory.py` → `interceptor.py`, `app.core.retriever.vector.defaults`, `app.services.agent.platform_config.load_platform_retrieval_configs`

## 设计决策

- **拦截位置**：`ChannelAgentExecutor.execute_stream` 中 `prepare_channel_execution` 之前，最大化跳过开销
- **双校验**：top1 score ≥ threshold **且** top1-top2 gap ≥ min_score_gap，避免模糊匹配误触发
- **不修改 harness**：复用 harness 的 EmbeddingService 和 VectorStore 接口，不引入反向依赖
- **Embedding 来源**：只从 WebUI 检索设置（`load_platform_retrieval_configs`）取配置，与 Memory/Curator/Cron 同一通道；不读 `EMBEDDING_*` 进程环境变量，未配置时返回 `None` 让调用方走正常 Agent 执行
- **配置热更新**：拦截器缓存键就是 embedding 配置（模型、密钥、地址；与 harness 的 embedding 服务缓存同一个键），每次取用都比对当前配置，变了就重建，没有重置钩子可漏接。UI 保存设置走的是 `POST /config/sync` 而不是 `PUT /config/{key}`，挂在单个路由上的重置会让拦截器一直停在旧模型上，而索引已按新模型重建，FAQ 随之静默失效直到重启。取配置走 `load_platform_retrieval_configs` 的短 TTL 缓存（保存配置即失效），所以这一次比对不额外读库；缓存不能取消：远程 Qdrant 每创建一次就是一个新客户端，逐条消息重建会逐条开连接
- **embedding 未配置**：返回 `None` 并丢弃已缓存的拦截器；读配置临时失败只让这一次返回 `None`，已缓存的拦截器保留
