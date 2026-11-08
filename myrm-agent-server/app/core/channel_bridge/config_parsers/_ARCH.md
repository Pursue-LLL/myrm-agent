# channel_bridge/config_parsers/

## 架构概述

渠道配置解析域：把前端 dict 解析成类型化配置。包根只保留门面与单域模块，回退链这组同域文件收进 `fallbacks/`。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 对外唯一入口，导出 `extract_*` / `build_*` / `resolve_*` / `merge_*` | ✅ |
| `common.py` | 支撑 | 数值兜底、模型配置合并、视频能力推断 | ✅ |
| `retrieval.py` | 模块 | embedding / reranker 配置解析 | ✅ |
| `mcp.py` | 模块 | MCP 配置解析与组织级合并 | ✅ |
| `voice.py` | 模块 | 语音与朗读配置 | ✅ |
| `session.py` | 模块 | 会话策略 | ✅ |
| `search.py` | 模块 | 搜索配置解析与可用性探测 | ✅ |
| `fallbacks/` | 子包 | 轻量/视觉/视频/槽位/后台进化回退链，详见 [fallbacks/_ARCH.md](fallbacks/_ARCH.md) | ✅ |

## 依赖

- `app.core.channel_bridge.model_resolver` — LiteLLM 模型名规范化
- `app.channels.types` — 会话与语音类型

## 依赖关系

- `retrieval.py` → `common.py`
- `voice.py` → `common.py`
