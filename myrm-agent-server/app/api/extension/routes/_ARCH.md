# routes/

Extension API sub-routers included by `router.py`.

## 架构概述

Wiki clip agent scope REST，与 WS/CDP 桥主 router 分离。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | 子路由包 | — |
| `clip_agent.py` | 路由 | **GET/PUT /extension/clip-agent** — UserConfig SSOT + MV3 WS push | ✅ |

## 依赖

- `app.services.extension.clip` (POS: clip target agent UserConfig)
- `app.services.extension.bridge::get_extension_bridge` (POS: MV3 WS push)
