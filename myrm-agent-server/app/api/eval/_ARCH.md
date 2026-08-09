# api/eval/

## 架构概述

评估套件调度与结果 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Exposes the evaluation framework to the Frontend and Control Plane. Includes single-profile eval endpoints (`/eval/run`, `/eval/stream`), WorkBuddy Bench endpoints (`/eval/wb-bench/sources`, `/eval/wb-bench/run`, `/eval/wb-bench/download`), cross-profile matrix eval endpoints (`/eval/matrix/run`, `/eval/matrix/stream`, `/eval/matrix/reports/latest`), and Memory A/B endpoints (`/eval/memory-ab/run`, `/eval/memory-ab/abort`, `/eval/memory-ab/status`, `/eval/memory-ab/stream`, `/eval/memory-ab/reports/latest`). | ✅ |
