# app/services/statistics

## 职责

统计域的**纯业务逻辑**层，与 HTTP 路由解耦。

## 组成

| 文件 | 职责 |
| --- | --- |
| `usage_aggregation.py` | 用量聚合纯逻辑（会话级聚合、路由/模型/隐私/cache 维度、Chat.total_* 缓存重建） |

## 依赖方向

- **输入**：`app.services.chat.chat_message`（tokenEconomics 快照）、assistant 消息 extra_data
- **输出**：`app.api.statistics.usage_aggregation`（API 层 re-export 薄壳）
- **禁止**：本层反向 import `app.api.*`（架构守门测试强制）
