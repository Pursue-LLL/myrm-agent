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
| `corpus.py` | FAQ 语料 CRUD + Qdrant 索引重建 |
| `interceptor.py` | 零 LLM 语义拦截器（embedding + 双校验） |
| `tracker.py` | 命中/未命中日志记录 + 分析统计 |
| `factory.py` | FaqInterceptor 延迟单例工厂 |

## 依赖关系

- `corpus.py` → `app.database.models.faq`, `myrm_agent_harness.toolkits.vector.base`, `myrm_agent_harness.toolkits.retriever.embedding.base`
- `interceptor.py` → `corpus.py`, 同上 harness 组件
- `tracker.py` → `app.database.models.faq.FaqHitLog`
- `factory.py` → `interceptor.py`, `app.core.retriever.vector.defaults`

## 设计决策

- **拦截位置**：`ChannelAgentExecutor.execute_stream` 中 `prepare_channel_execution` 之前，最大化跳过开销
- **双校验**：top1 score ≥ threshold **且** top1-top2 gap ≥ min_score_gap，避免模糊匹配误触发
- **不修改 harness**：复用 harness 的 EmbeddingService 和 VectorStore 接口，不引入反向依赖
