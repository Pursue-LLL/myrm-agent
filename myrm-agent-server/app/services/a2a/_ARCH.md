# app/services/a2a

## Overview

A2A (Agent-to-Agent) service layer for inter-agent discovery, task persistence, audit logging, and webhook dispatch.
Implements the service backend for standard Google A2A protocol integration.

## Files

| File | Role |
|------|------|
| `audit.py` | `A2AAuditLogger` 结构化审计日志记录器，持久化 A2A 请求与状态流转至 `a2a_audit.jsonl` |
| `card_generator.py` | `AgentCardGenerator` 动态生成标准 Google A2A v1.0 AgentCard 清单 |
| `task_store.py` | `A2ATaskStore` 内存安全带上限 A2A 任务状态持久化存储仓储，支持状态过滤索引 |
| `peer_registry.py` | `A2APeerRegistryService` 可信远程 A2A 节点注册、入站凭据白名单匹配鉴权、AES-256-GCM 凭证托管、探活探测（Probe）与 SSRF 阻断 |
| `webhook_sender.py` | `A2AWebhookSender` 异步 Webhook 通知推送器，带 HMAC-SHA256 签名与指数退避重试 |
| `service.py` | `A2AServerService` 核心任务调度与生命周期编排服务，集成 UntrustedExecutionFence 运行时特权剥离围栏、wrap_untrusted 提示词防投毒 5 层安全信封与人工审批流 |
| `__init__.py` | 服务层统一导出入口 |
