# subagent_watchdog/

## Overview
Subagent execution heartbeat watchdog and zombie cleanup suite.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Subagent execution heartbeat watchdog and zombie cleanup suite. | — |
| `subagent_heartbeat_tracker.py` | Core | Subagent execution heartbeat tracker and tiered health evaluator. | ✅ |
| `watchdog_types.py` | Core | Strongly typed contracts for subagent execution heartbeat watchdog and zombie cleanup. | ✅ |
| `zombie_cleanup_supervisor.py` | Core (not wired) | Tiered progressive timeout watchdog: warning → soft cancel → hard terminate, with a bounded reap so a supervised coroutine never outlives its verdict. **No production caller yet** — live subagent runs go through `agent/sub_agents/_manager_spawn.py` and `agent/sub_agents/teams/engine.py`, which own their own timeout and cancellation. Wire this in before treating zombie reaping as an active capability. | ✅ |
