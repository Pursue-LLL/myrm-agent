# browser_recording/

## Overview

Browser Skill Recording Wizard API. Provides WebSocket for real-time recording
control and REST endpoints for session queries and skill generation.

On `start`, the WebSocket handler automatically binds to the active Agent's
Playwright Page via `ActionCaptureEngine`, capturing DOM events and forwarding
structured `ActionStep`s (with screenshots) to the frontend in real-time.
Falls back to manual step injection when no active browser session exists.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Module entry — exports `router` | — |
| `schemas.py` | Contract | Pydantic request/response models | ✅ |
| `router.py` | Core | WebSocket `/ws/recording` + REST endpoints + CaptureEngine integration | ✅ |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| WebSocket | `/ws/recording` | Real-time recording control (start/stop/pause/resume/step/delete_step) |
| GET | `/recording/sessions` | List active recording sessions |
| GET | `/recording/sessions/{id}` | Get session details with steps |
| POST | `/recording/generate-skill` | Generate Browser Skill from completed session |

## Data Flow

1. Frontend sends `{type: "start"}` via WebSocket
2. Server resolves the active `BrowserSession` via `AgentGateway`
3. If a Playwright Page exists: creates `ActionCaptureEngine`, injects JS capture script, registers `_WsStepForwarder` callback → **auto mode**
4. If no Page: creates empty `CaptureSession` → **manual mode** (steps injected by frontend)
5. Captured steps are forwarded to frontend in real-time via WebSocket

## Dependencies

- `app.services.browser_recording.session_manager` — in-memory session lifecycle
- `app.services.browser_recording.skill_generator` — SKILL.md generation + credential detection
- `app.services.agent.gateway` — access to active `BrowserSession` via `AgentGateway`
- `app.core.infra.ws_origin_guard` — WebSocket origin verification
- `myrm_agent_harness.toolkits.browser.action_capture` — `ActionCaptureEngine`, action types, serialization
