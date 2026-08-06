# clip/

Browser extension wiki clip orchestration — multipart size guard + async job runner.

## File Index

| File | Role | Description | I/O/P |
| --- | --- | --- | --- |
| `form.py` | Guard | `MAX_CLIP_PAYLOAD_BYTES` + `clip_form_payload_bytes` | ✅ |
| `runner.py` | Core | `schedule_wiki_clip` / `get_wiki_clip_job` → harness `publish_clip_ingress` · post-write `publish_wiki_ingest_snapshot` + dedup scan | ✅ |
| `__init__.py` | Package | Public exports | — |

## Callers

| Caller | Entry |
| --- | --- |
| `app/api/wiki/routes/clip.py` | REST `/wiki/clip` + job poll |
| Tests | `tests/api/wiki/test_wiki_clip_api.py` |

## Dependencies

- `myrm_agent_harness.toolkits.wiki.pipeline.ingress` (POS: clip ingress SSOT)
- `app.services.wiki.vault_service` (POS: wiki archiver)
- `app.services.wiki.dedup_runner` (POS: post-clip dedup scan)
- `app.services.wiki.ingest_events` (POS: Settings Wiki ingest SSE tree/stats refresh)
