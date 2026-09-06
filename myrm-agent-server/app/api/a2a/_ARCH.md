# app/api/a2a

## Overview

A2A (Agent-to-Agent) Provider Server API endpoints implementing standard Google A2A v1.0
discovery manifests and JSON-RPC 2.0 task lifecycle routing.

## Files

| File | Role |
|------|------|
| `router.py` | FastAPI APIRouter registering `/.well-known/agent-card.json` and `/rpc` task dispatch |
