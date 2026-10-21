# app/api/a2a

## Overview

A2A (Agent-to-Agent) Provider Server API endpoints implementing standard Google A2A v1.0
discovery manifests and JSON-RPC 2.0 task lifecycle routing.

## Files

| File | Role |
|------|------|
| `router.py` | FastAPI APIRouter registering `/.well-known/agent-card.json`, `/rpc` task dispatch with inbound peer whitelist zero-trust gating, and `/tasks/pending-approval`, `/tasks/{task_id}/approve`, `/tasks/{task_id}/reject` approval lifecycle endpoints |
