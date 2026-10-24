# runtime_zombie_reaper/

## Overview
Agent process & causality tree dashboard, orphan process cascading reaper watchdog, deadlock polling active breaker, and cross-profile activity monitor suite.
Targets the three failure modes that leak agents: orphan helper processes, dead subagent deadlock polling, and un-reaped process trees.
Tracks PGID process trees across parent agents, delegated subagents, and helper processes (Playwright/Python/MCP), cascades SIGTERM/SIGKILL physical termination upon agent detach, and injects failure faults to interrupt infinite polling.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package Facade | Public re-exports of causality tracker and data models. | ✅ |
| `models.py` | Domain Models | Pydantic schemas for ProcessCausalityNode, ProfileResourceUsage, PostMortemTaskEntry, and RuntimeCausalitySnapshot. | ✅ |
| `tracker.py` | Core Tracker | AgentRuntimeCausalityTracker managing process trees, orphan reaping, deadlock detection, and failed runs. | ✅ |
