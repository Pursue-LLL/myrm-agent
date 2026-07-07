# tasks 模块架构

## 架构概述

异步任务系统。提供后台任务定义、执行器和 worker 管理。支持图片生成等异步处理。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 任务类型和 worker 导出 | — |
| `worker.py` | 核心 | 任务 worker 主循环。优先级调度、并发控制、超时处理、重试策略、缓存复用。通过 `on_status_change` 回调在每次状态变化时发布事件到 SSE 流 | ✅ |
| `events.py` | 核心 | TaskEventBus：内存 pub/sub 事件总线，SSE 订阅者实时接收 task_update 事件 | ✅ |
| `metrics.py` | 辅助 | 任务指标采集 | — |
| `cleanup.py` | 辅助 | 任务清理（`_db_maintenance_job` 每 6h 调用） | — |
| `image_config_resolver.py` | 核心 | 从 task payload 快照还原 `ImageGenerationConfig`（含 media callback）；密钥经 `task_payload_crypto` 在 persist 前加密 | ✅ |
| `task_payload_crypto.py` | 核心 | persist 前 seal `api_key` / `gateway_config.auth_token`；worker resolver 仅 open 加密字段 | ✅ |
| `executors/` | 子模块 | 具体任务执行器 | — |

## 子模块

| 模块 | 职责 |
|------|------|
| `executors/` | 图片生成等具体任务执行器 |
