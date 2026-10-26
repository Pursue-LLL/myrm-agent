# routes/

Wiki API sub-routers included by `router.py`.

## 架构概述

Extension clip、wikiignore 与 ima 导入 REST 子路由，与 Brain Console 主 router 分离。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | 入口 | 子路由包 | — |
| `clip.py` | 路由 | **POST/GET /clip** · **GET/PUT /wikiignore** | ✅ |
| `ima.py` | 路由 | **GET /sources/ima**（聚合状态）· **PUT/DELETE /sources/ima/credentials**（写入前先向 ima 校验；API Key 只写不回显）· **GET /sources/ima/libraries** · **PUT /sources/ima/config** · **POST /sources/ima/sync/{start,pause,resume,retry-failed}**（`start` 也承担「立即检查」：已有任务则立刻触发下一轮；`retry-failed` 只重排当前所选范围） · **POST /sources/ima/compile**（只编译 ima 已导入且属于当前所选知识库/笔记的文档，与卡片计数口径一致；去重待审 409）· **GET /sources/ima/items?bucket=attention\|lossy\|remote_deleted**；错误一律 `{code, message}`，不透传上游原文 | ✅ |

## 依赖

- `app.services.wiki.clip` (POS: clip job orchestration + multipart cap)
- `app.services.wiki.source_sync.ima` (POS: ima sync facade)
- `app.services.wiki.vault` (POS: wiki archiver)
- `myrm_agent_harness.toolkits.wiki.pipeline.ingress` (POS: clip ingress + wikiignore)
