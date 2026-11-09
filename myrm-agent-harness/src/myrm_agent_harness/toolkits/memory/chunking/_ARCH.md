# chunking/ 架构说明

## 模块定位
对话切片策略：把消息序列按交换对 / 仅用户 / 整会话 / 情景切成语义单元，供原文存储、记忆迁移与抽取使用。

## 文件清单

| 文件名 | 职责 |
|---|---|
| `__init__.py` | 包门面导出，导出对话切片策略 |
| `conversation.py` | 对话切片策略：`ChunkingStrategy`（交换对 / 仅用户 / 整会话 / 情景）、`ConversationChunk`、按空闲间隔与上下文预算切分并带因果滑动重叠的 `EpisodesChunker`，入口 `chunk_conversation()` |
