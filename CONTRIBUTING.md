# Contributing to myrm-agent

Thank you for helping improve MyrmAgent. This repository is the MIT-licensed product monorepo (server, Web UI, desktop).

## Before you start

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) for five-repo boundaries and deployment modes.
2. Read [_ARCH.md](_ARCH.md) for directory responsibilities.
3. Agent execution lives in the closed-source PyPI package `myrm-agent-harness` — do not vendor harness source here.

## Documentation reading path (~30 min)

Use this order on your first contribution — you do not need to read all 300+ `_ARCH.md` files upfront.

| Step | Read | Why |
|------|------|-----|
| 1 | [ARCHITECTURE.md](ARCHITECTURE.md) | Five-repo boundaries, three deployment modes, harness vs server split |
| 2 | [_ARCH.md](_ARCH.md) | Top-level package map (server / frontend / desktop / extension / shared) |
| 3 | Area you will touch | Server: [app/_ARCH.md](myrm-agent-server/app/_ARCH.md) · Frontend: [src/components/_ARCH.md](myrm-agent-frontend/src/components/_ARCH.md) · Desktop: [myrm-agent-desktop/_ARCH.md](myrm-agent-desktop/_ARCH.md) · Extension: [myrm-agent-extension/_ARCH.md](myrm-agent-extension/_ARCH.md) |
| 4 | Target subdirectory `_ARCH.md` | File table for the module you are editing (CI requires keeping it in sync) |
| 5 | Deep dive (optional) | Server channels: [CHANNELS_SYSTEM.md](myrm-agent-server/app/channels/CHANNELS_SYSTEM.md) · Full server layering: [myrm-agent-server/ARCHITECTURE.md](myrm-agent-server/ARCHITECTURE.md) |

For channels work, use [task path C](#c--channels-im--webhook) below (three-layer map).

**Fractal docs:** each directory under `myrm-agent-server/app/` has `_ARCH.md` (not README). Frontend route folders under `src/app/*` are thin shells and share [src/app/_ARCH.md](myrm-agent-frontend/src/app/_ARCH.md) (no per-route `_ARCH.md`). Update the nearest `_ARCH.md` when you add or move files — see [Documentation convention](#documentation-convention) below.

### Task-specific paths (pick one)

#### A — Backend HTTP or business logic

| Step | Read |
|------|------|
| 1 | [ARCHITECTURE.md](ARCHITECTURE.md) → [app/_ARCH.md](myrm-agent-server/app/_ARCH.md) |
| 2 | Target [api/*/_ARCH.md](myrm-agent-server/app/api/_ARCH.md) **and** the mapped [services/*/_ARCH.md](myrm-agent-server/app/services/_ARCH.md) ([vocabulary table](#api--services-domain-vocabulary) below) |
| 3 | Open the route handler you will edit and trace imports — some routes call harness or `database/` directly with **no** `services/` folder |
| 4 | Run fractal + line-budget checks (see [Documentation convention](#documentation-convention)) |

#### B — Web UI

| Step | Read |
|------|------|
| 1 | [myrm-agent-frontend/_ARCH.md](myrm-agent-frontend/_ARCH.md) → [src/components/_ARCH.md](myrm-agent-frontend/src/components/_ARCH.md) |
| 2 | Route shell: [src/app/_ARCH.md](myrm-agent-frontend/src/app/_ARCH.md) — keep `app/*` thin; put UI in `components/features/*` |
| 3 | Cross-feature widgets (not under `features/`): `components/agent/`, `auth/`, `billing/`, `security/`, `approval/`, `layout/`, `primitives/` |
| 4 | API clients: [src/services/_ARCH.md](myrm-agent-frontend/src/services/_ARCH.md) · State: [src/store/_ARCH.md](myrm-agent-frontend/src/store/_ARCH.md) |
| 5 | User-facing copy: `locales/en.json` + `locales/zh.json` · Verify: `bun run build` |

#### C — Channels (IM / webhook)

| Step | Read |
|------|------|
| 1 | [ARCHITECTURE.md § Channels](ARCHITECTURE.md) → [CHANNELS_SYSTEM.md](myrm-agent-server/app/channels/CHANNELS_SYSTEM.md) |
| 2 | Framework: [app/channels/_ARCH.md](myrm-agent-server/app/channels/_ARCH.md) (Provider / Gateway / Routing) |
| 3 | Business pairing: [app/services/channels/_ARCH.md](myrm-agent-server/app/services/channels/_ARCH.md) |
| 4 | Agent binding: [app/core/channel_bridge/_ARCH.md](myrm-agent-server/app/core/channel_bridge/_ARCH.md) |
| 5 | HTTP admin / webhook: [app/api/channels/_ARCH.md](myrm-agent-server/app/api/channels/_ARCH.md) |

## Development setup

```bash
# From repo root
bash scripts/install.sh   # or: myrm setup
myrm start                # backend :8080 + frontend :3000
```

Manual split:

```bash
cd myrm-agent-frontend && bun install && bun run dev
myrm dev                  # backend only
```

See [scripts/_ARCH.md](scripts/_ARCH.md) for CLI details.

## Where to change code

| Area | Path | Layering |
|------|------|----------|
| HTTP routes | `myrm-agent-server/app/api/` | Thin handlers; no business logic |
| Business logic | `myrm-agent-server/app/services/` | Orchestration, calls `core/` + harness |
| Shared DTOs | `myrm-agent-server/app/schemas/` | Pydantic contracts for api ↔ services (no business logic) |
| Agent definitions | `myrm-agent-server/app/ai_agents/` | Agent config, middleware, tools |
| Domain primitives | `myrm-agent-server/app/core/` | Reusable capabilities, adapters |
| Data layer | `myrm-agent-server/app/database/` | ORM + repositories (anti-corruption boundary) |
| Harness adapters | `myrm-agent-server/app/adapters/` | Protocol implementations into harness |
| Platform modes | `myrm-agent-server/app/platform_utils/` | Local vs sandbox deployment differences |
| Process boot | `myrm-agent-server/app/startup/` · `app/server/` | Env, lock, uvicorn, FastAPI lifespan |
| Runtime schedulers | `myrm-agent-server/app/lifecycle/` | Gateway, cron, kanban dispatch, guardians |
| Background jobs | `myrm-agent-server/app/tasks/` | Async executors (image gen, etc.) |
| HTTP middleware | `myrm-agent-server/app/middleware/` | Auth, security, rate limits |
| Channels framework | `myrm-agent-server/app/channels/` | Provider bus, routing (see `CHANNELS_SYSTEM.md`) |
| Web UI | `myrm-agent-frontend/src/` | Next.js; product UI in `features/` by domain; shared cross-feature primitives in `components/agent/`, `auth/`, `billing/`, `security/`, `approval/`, `error-boundary/`, `layout/`, `primitives/` |
| Desktop shell | `myrm-agent-desktop/` | Tauri + sidecar packaging |
| Browser extension | `myrm-agent-extension/` | Chrome MV3 CDP bridge (WebSocket client) |
| Shared static config | `shared/` | Cross-end JSON; server Docker copies to `/shared`; frontend `@shared/*` in dev/build |

**Dependency direction:** `api → services → ai_agents → core`. Never import `app.api` from `services/`.

## API ↔ Services domain vocabulary

`api/` and `services/` are **not** a 1:1 mirror. Folder names differ on purpose (HTTP resource plural vs service singular) or because logic lives in harness / `core/` / `database/` instead of `services/`.

**CI lock:** `myrm-agent-server/tests/architecture/test_api_services_vocabulary.py` must stay aligned with this section (same-name set, api-only set, services-only set, and `API_SERVICES_ALIASES`).

### Same folder name (start here)

These domains use matching names under both layers:

`approvals` · `audit` · `budget` · `channels` · `checkpoint` · `companion` · `config` · `connect` · `context` · `extension` · `features` · `files` · `integrations` · `kanban` · `memory` · `message_filter` · `migration` · `risk` · `security` · `skill_optimization` · `skills` · `webui` · `wiki`

### Intentional name pairs (most common confusion)

| HTTP route tree (`api/`) | Business layer (`services/`) | Notes |
|--------------------------|------------------------------|-------|
| `agents/` | `agent/` | Streaming runs, templates, sub-agents, goals (`api/goals/` → `services/agent/`) |
| `chats/` | `chat/` | Session CRUD, compaction, message handling |
| `projects/` | `project/` | Project CRUD and chat assignment |
| `events/` | `event/` | Agent runtime event persistence |
| `background_tasks/` | `background/` | Long-running worker jobs (UI panel) |
| `batch_optimization/` | `skill_optimization/` | Batch skill optimization flows |
| `credentials/` | `integrations/` (+ `config/`) | OAuth / MCP credential slots |
| `api_keys/` | `config/` | API key storage and rotation |
| `system/` · `health/` | `infra/` · `power/` | Ops, shutdown, sleep inhibition |
| `files/` (HTTP upload) | `files/` (bytes→text) + `artifacts/` | Deploy bundles and share tokens often touch `services/artifacts/` |

### `api/` only — no sibling `services/<same-name>/`

Thin HTTP, harness, or DB-direct routes. Find logic in the linked column before adding a new `services/` folder.

| `api/` | Where logic lives |
|--------|-------------------|
| `agents/` · `goals/` | `services/agent/` |
| `chats/` · `projects/` | `services/chat/` · `services/project/` |
| `calendar/` | `database/models` (+ optional `core/calendar/`) |
| `workspace/` | harness workspace rules scanner (see `api/workspace/_ARCH.md`) |
| `datasets/` | harness event-log export pipeline |
| `eval/` | `core/eval/` (+ harness eval executors) |
| `openai_compat/` | `services/agent/` streaming + `services/config/` |
| `remote_access/` | `app/remote_access/` (pair tokens, tunnel, mobile hub gate) |
| `voice/` · `stt/` · `tts/` · `media/` | `core/media/`, `services/agent/`, `app/tasks/` |
| `cron/` | `core/cron/` + `services/kanban/` dispatch |
| `tasks/` | `app/tasks/` executors |
| `mcp/` | `services/connect/` MCP endpoint + `services/agent/` platform config |
| `external_agents/` | harness ACP subscription auth (CLI login SSE) |
| `commitment/` | `core/commitment/` |
| `notifications/` | `core/channel_bridge/` (gateway push) |
| `statistics/` | `api/statistics/*` aggregators + `database/` |
| `internal/` | Control Plane internal bridge (SaaS) |
| `client_logs/` | ingest only — no business service |

### `services/` only — no matching `api/<same-name>/`

Called from other HTTP trees or lifecycle hooks:

| `services/` | Typical caller |
|-------------|----------------|
| `auth/` | middleware, `api/webui/`, OAuth callbacks |
| `artifacts/` · `deploy/` | `api/files/`, artifact pages |
| `mascot/` | SSE from `services/agent/` stream (companion XP) |
| `repair/` | `api/health/` repair-action endpoints |
| `locked_use/` | Computer Use / Tauri IPC orchestration |
| `event/` | `api/events/`, agent stream persistence |

**Rule of thumb:** add HTTP in `api/`; add orchestration in `services/`; add reusable primitives in `core/`; never duplicate harness execution logic in server.

## Documentation convention

Each directory under `myrm-agent-server/app/` must have `_ARCH.md` (not README). When you add or move files:

1. Update the directory's `_ARCH.md` file table.
2. Update parent `_ARCH.md` if module membership changes.
3. Run from `myrm-agent-server/`:

```bash
.venv/bin/python scripts/check_fractal_docs.py
.venv/bin/python scripts/check_fractal_docs.py --no-stub
.venv/bin/python scripts/check_file_line_budget.py
```

CI enforces fractal docs, no-stub guards on `api/` and `channels/providers/`, line-budget gate, and `tests/architecture/test_api_services_vocabulary.py` (keep in sync with the vocabulary section below).

`scripts/sync_arch_file_tables.py` only refreshes stub `_ARCH.md` (markers `待补` / `（见目录）`) and skips directories that already have a substantive `## 架构概述`. Do not run it with `--force` on rich module docs (e.g. `services/memory/`, `core/skills/`).

## Pull requests

1. Keep changes scoped to one concern.
2. Add or update tests in `myrm-agent-server/tests/` when behavior changes.
3. Run server tests: `cd myrm-agent-server && .venv/bin/python -m pytest`
4. For frontend UI changes, run `cd myrm-agent-frontend && bun run build`
5. Do not commit secrets (`.env`, credentials, `.myrm/` runtime data).

## Code style

- **Python:** Ruff + type hints (no `Any`). English for errors and logs.
- **Frontend:** Bun, Next.js, Tailwind. User-facing copy must be bilingual (`locales/en.json` + `locales/zh.json`).
- **File size:** Prefer modules under ~400 lines; split when a file grows beyond ~500 lines.

## Questions

Open a GitHub issue for bugs or feature proposals. For architecture questions, cite the relevant `_ARCH.md` or `ARCHITECTURE.md` section in your issue.
