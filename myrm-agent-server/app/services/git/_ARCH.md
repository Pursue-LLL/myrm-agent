# Git Services Subsystem Architecture

## Overview
Git services encapsulate multi-worktree lifecycle management, active worktree switching, session-to-checkout anchor resolution, and touched file tracking.

## Components & Files
| File | Role | Primary Callers |
|---|---|---|
| `worktree_service.py` | Worktree lifecycle, active switching, checkout anchoring & touched files | `app/api/git/worktree_router.py` |
| `__init__.py` | Export facade for git service layer | External modules |
