# app/services/webhook/

## Overview
Business services for dispatching lifecycle webhook events to external endpoints.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Webhook service package | ✅ |
| `lifecycle_webhook_service.py` | Core | Lifecycle webhook dispatcher with retry and HMAC-SHA256 request signing; subscribes to AppEventBus (`session_completed`, `session_failed`, `subagent_spawned`, `subagent_merged`, approval, kanban, goal) | ✅ |
