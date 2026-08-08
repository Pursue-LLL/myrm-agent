# routes/

Wiki API sub-routers included by `router.py`.

## 架构概述

Extension clip 与 wikiignore REST 子路由，与 Brain Console 主 router 分离。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | 子路由包 | — |
| `clip.py` | 路由 | **POST/GET /clip** · **GET/PUT /wikiignore** | ✅ |

## 依赖

- `app.services.wiki.clip` (POS: clip job orchestration + multipart cap)
- `app.services.wiki.vault` (POS: wiki archiver)
- `myrm_agent_harness.toolkits.wiki.pipeline.ingress` (POS: clip ingress + wikiignore)
