# app/core/vision 模块架构

## 架构概述

Server 层视觉媒体路由 SSOT：解析 Settings 中的图/视频降级槽位，为 `chat_utils` 预处理提供路由决策。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `media_router.py` | 核心 | `VisionMediaRoute` / `resolve_image_route` / `resolve_video_route` / `pick_video_fallback_configs`（委托 harness SSOT） | ✅ |

## 依赖

- **输入**：`app.core.types.ModelConfig`（来自 `config_parsers` 解析的 providers_dict）
- **被依赖**：`app.core.utils.chat_utils`（图片/视频预处理）、`GeneralAgent._build_runtime_context`（agent sandbox 媒体 context）
