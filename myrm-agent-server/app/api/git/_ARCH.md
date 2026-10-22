# Git API Subsystem Architecture

## Overview
Exposes REST endpoints for Git Worktree operations (list, create, switch, delete) and session checkout anchoring / touched files inspection.

## Components & Files
| File | Role | Primary Consumers |
|---|---|---|
| `worktree_router.py` | FastAPI APIRouter for `/git` endpoints | `app/api/router.py` |
| `__init__.py` | Package export facade | External importers |
