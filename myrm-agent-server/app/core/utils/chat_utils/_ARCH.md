# app/core/utils/chat_utils 子包架构

聊天工具子域。把框架层的聊天/图片原语扩展成业务语义：历史转换、judge 判定解析、图片压缩与入站多模态预处理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合导出公开 helper（`ChatHistoryReq`/`convert_chat_history`/`parse_judge_json` 等）与测试使用的私有 helper | — |
| `history.py` | 核心 | `convert_chat_history`（前端历史 → LangChain 消息，含 `__agent_history` 还原与旧图片降级）、`parse_judge_json`（`done` 键语义） | ✅ |
| `images.py` | 辅助 | 旧图片降级、base64 压缩判定与压缩（`_degrade_old_images` / `_needs_compression_base64` / `_compress_base64_image`） | ✅ |
| `multimodal.py` | 核心 | `preprocess_inbound_multimodal_query`（非 Web 渠道入站多模态预处理）与 `_process_human_content` 分发 | ✅ |
| `image_items.py` | 核心 | `_process_image_item`：本地 URL → base64、超限压缩、视觉 fallback | ✅ |
| `video_items.py` | 核心 | `_process_video_item`：抽帧并组装视觉载荷 | ✅ |

## 依赖关系

- 上游：`myrm_agent_harness.utils.chat_utils / image_utils / json_parsing / media.image_compressor`、`app.core.utils.files_utils`
- 下游：`app/core/kanban/verifier.py`、`app/services/agent/stream_session/*`、`app/services/memory/import_flows/*`、`app/services/chat/chat_title.py` 等
