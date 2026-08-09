# api/eval/

## 架构概述

评估套件调度与结果 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `streaming.py` | 助手 | Shared SSE status streaming for eval endpoints: `stream_status_events(status_getter)` emits deduplicated `data:` frames and closes on `is_running=false`. Reused by the single-profile eval, matrix, and memory A/B status streams so the SSE framing contract lives in one place. | ✅ |
| `router.py` | 路由 | Exposes the evaluation framework to the Frontend and Control Plane. Aggregates single-profile eval endpoints (`/eval/run`, `/eval/stream`), WorkBuddy Bench endpoints (`/eval/wb-bench/sources`, `/eval/wb-bench/run`, `/eval/wb-bench/download`), dataset/case management, reports and the internal anonymized metrics endpoint. Includes `matrix_router` + `memory_ab_router` so all eval endpoints stay under the `/eval` prefix. | ✅ |
| `matrix_router.py` | 路由 | Cross-profile matrix eval endpoints (`/eval/matrix/run`, `/eval/matrix/abort`, `/eval/matrix/status`, `/eval/matrix/stream`, `/eval/matrix/reports/latest`) as a self-contained sub-router under the `/eval` prefix. | ✅ |
| `memory_ab_router.py` | 路由 | Memory A/B endpoints (`/eval/memory-ab/run`, `/eval/memory-ab/abort`, `/eval/memory-ab/status`, `/eval/memory-ab/stream`, `/eval/memory-ab/reports/latest` + `/history` + `/reports/{timestamp}`). The `/eval/memory-ab/run` endpoint validates that an embedding model is both configured and reachable before starting the run (via `verify_platform_embedding_ready`, a structural check plus a real embedding probe), returning an explicit error otherwise — a missing or unusable embedding backend makes the memory-on arm silently degrade to a memory-free agent and produce a misleading "memory has no effect" result. A post-probe synchronous re-check of `is_running` closes the concurrent-start race window. | ✅ |
