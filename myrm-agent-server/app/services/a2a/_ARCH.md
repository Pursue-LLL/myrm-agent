# app/services/a2a

## Overview

A2A (Agent-to-Agent) service layer for inter-agent discovery, task persistence, audit logging, and webhook dispatch.
Implements the service backend for standard Google A2A protocol integration.

## Files

| File | Role |
|------|------|
| `audit.py` | `A2AAuditLogger` 结构化审计日志记录器，持久化 A2A 请求与状态流转至 `a2a_audit.jsonl` |
| `card_generator.py` | `AgentCardGenerator` 动态生成标准 Google A2A v1.0 AgentCard 清单 |
| `task_store.py` | `A2ATaskStore` 内存安全带上限 A2A 任务状态持久化存储仓储 |
| `webhook_sender.py` | `A2AWebhookSender` 异步 Webhook 通知推送器，带 HMAC-SHA256 签名与指数退避重试 |
| `service.py` | `A2AServerService` 核心任务调度与生命周期编排服务，实现 `A2ATaskService` |
| `__init__.py` | 服务层统一导出入口 |
