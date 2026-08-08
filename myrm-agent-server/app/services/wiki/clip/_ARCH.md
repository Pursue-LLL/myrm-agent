# clip/

Browser extension wiki clip orchestration — multipart size guard + async job runner.

## 架构概述

Server 侧 clip 任务编排：multipart 大小守卫 + 异步 job runner，委托 harness `publish_clip_ingress` 写入 raw/。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `form.py` | 守卫 | `MAX_CLIP_PAYLOAD_BYTES` + `clip_form_payload_bytes` | ✅ |
| `runner.py` | 核心 | `schedule_wiki_clip` / `get_wiki_clip_job` → harness ingress · post-write ingest SSE + dedup scan | ✅ |
| `__init__.py` | 入口 | Public exports | — |

## 调用方

| Caller | Entry |
| --- | --- |
| `app/api/wiki/routes/clip.py` | REST `/wiki/clip` + job poll |
| Tests | `tests/api/wiki/test_wiki_clip_api.py` · `tests/services/extension/clip/test_agent_config.py` |

## 依赖

- `myrm_agent_harness.toolkits.wiki.pipeline.ingress` (POS: clip ingress SSOT)
- `app.services.wiki.vault` (POS: wiki archiver)
- `app.services.wiki.dedup_runner` (POS: post-clip dedup scan)
- `app.services.wiki.ingest_events` (POS: Settings Wiki ingest SSE tree/stats refresh)

## 产品默认

- Extension sends `folder_path=""` → harness `_default_clip_path` writes under `clips/{YYYY-MM}/web_{sha12(source_url)}.md`.
- Extension sends `queue_compile=false` → zero-LLM clip; users compile explicitly from Settings Wiki.
- Clip ingress runs Track A (multipart assets) then Track B (`secure_get` for remaining remote markdown images).
- Same `source_url` re-clip replaces existing raw when frontmatter `source_url` matches (extension caller only).
- REST `queue_compile=true` remains for advanced/API callers only.

## Wiki clip defaults

| Field | Extension value | Effect |
|-------|-----------------|--------|
| `folder_path` | `""` | Harness writes to `clips/{YYYY-MM}/web_{sha12(source_url)}.md` |
| `queue_compile` | `false` | Zero-LLM clip; compile explicitly from Settings Wiki |
