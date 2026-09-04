# Evidence Playback Service Architecture

This module provides evidence playback and provenance inspection for the Memory Command Center.

## Module Role & Directory Boundary
- Directory: `app/services/memory/evidence`
- Layer: Server Business Service
- Role: Extracts and redacts historical conversation turns surrounding memory extraction points for auditability and verification.

## Files
| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `playback_service.py` | Service | 记忆证据溯源回放服务，提供交互对话切片检索与脱敏 | ✅ |
