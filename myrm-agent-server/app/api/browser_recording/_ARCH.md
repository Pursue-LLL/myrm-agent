# browser_recording/

## Overview

Browser Skill Recording Wizard API. Provides WebSocket for real-time recording
control and REST endpoints for session queries and skill generation.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Module entry — exports `router` | — |
| `schemas.py` | Contract | Pydantic request/response models | ✅ |
| `router.py` | Core | WebSocket `/ws/recording` + REST endpoints | ✅ |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| WebSocket | `/ws/recording` | Real-time recording control (start/stop/pause/resume/step/delete_step) |
| GET | `/recording/sessions` | List active recording sessions |
| GET | `/recording/sessions/{id}` | Get session details with steps |
| POST | `/recording/generate-skill` | Generate Browser Skill from completed session |

## Dependencies

- `app.services.browser_recording.session_manager` — in-memory session lifecycle
- `app.services.browser_recording.skill_generator` — SKILL.md generation + credential detection
- `app.core.infra.ws_origin_guard` — WebSocket origin verification
- `myrm_agent_harness.toolkits.browser.action_capture` — action types and serialization
