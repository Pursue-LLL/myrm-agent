# api/eval/

## 架构概述

评估套件调度与结果 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `streaming.py` | 助手 | Shared SSE status streaming for eval endpoints: `stream_status_events(status_getter)` emits deduplicated `data:` frames and closes on `is_running=false`. Reused by the single-profile eval, matrix, and memory A/B status streams so the SSE framing contract lives in one place. | ✅ |
| `router.py` | 路由 | Exposes the evaluation framework to the Frontend and Control Plane. Aggregates single-profile eval endpoints (`/eval/run`, `/eval/stream`), dataset/case management, reports and the internal anonymized metrics endpoint. Includes `benchmarks_router` + `matrix_router` + `memory_ab_router` so all eval endpoints stay under the `/eval` prefix. | ✅ |
| `benchmarks_router.py` | 路由 | External benchmark endpoints (`/eval/benchmarks` list, `/eval/benchmarks/run`, `/eval/benchmarks/download` + legacy `/eval/wb-bench/sources`, `/eval/wb-bench/run`, `/eval/wb-bench/download`) as a self-contained sub-router under the `/eval` prefix. | ✅ |
| `matrix_router.py` | 路由 | Cross-profile matrix eval endpoints (`/eval/matrix/run`, `/eval/matrix/abort`, `/eval/matrix/status`, `/eval/matrix/stream`, `/eval/matrix/reports/latest`) as a self-contained sub-router under the `/eval` prefix. | ✅ |
| `memory_ab_router.py` | 路由 | Memory A/B endpoints (`/eval/memory-ab/run`, `/eval/memory-ab/abort`, `/eval/memory-ab/status`, `/eval/memory-ab/stream`, `/eval/memory-ab/reports/latest` + `/history` + `/reports/{timestamp}`). The `/eval/memory-ab/run` endpoint validates the environment before starting the run: an embedding model must be configured and reachable (via `verify_platform_embedding_ready`, a structural check plus a real embedding probe) — a missing or unusable embedding backend makes the memory-on arm silently degrade to a memory-free agent; and when the benchmark's tool whitelist declares `web_search` (e.g. BrowseComp), a search provider must be configured and reachable — a missing search backend silently produces a near-zero score on both arms. Both checks return explicit errors otherwise, mirroring the benchmark-run pre-flight. A post-probe synchronous re-check of `is_running` closes the concurrent-start race window. | ✅ |
