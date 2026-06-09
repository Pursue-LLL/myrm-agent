# Contributing to myrm-agent

Thank you for helping improve MyrmAgent. This repository is the MIT-licensed product monorepo (server, Web UI, desktop).

## Before you start

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) for five-repo boundaries and deployment modes.
2. Read [_ARCH.md](_ARCH.md) for directory responsibilities.
3. Agent execution lives in the closed-source PyPI package `myrm-agent-harness` — do not vendor harness source here.

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
| Agent definitions | `myrm-agent-server/app/ai_agents/` | Agent config, middleware, tools |
| Domain primitives | `myrm-agent-server/app/core/` | Reusable capabilities, adapters |
| Channels framework | `myrm-agent-server/app/channels/` | Provider bus, routing (see `CHANNELS_SYSTEM.md`) |
| Web UI | `myrm-agent-frontend/src/` | Next.js; `features/` by product domain |
| Desktop shell | `myrm-agent-desktop/` | Tauri + sidecar packaging |
| Browser extension | `myrm-agent-extension/` | Chrome MV3 CDP bridge (WebSocket client) |
| Shared static config | `shared/` | Cross-end JSON; server Docker copies to `/shared`; frontend `@shared/*` in dev/build |

**Dependency direction:** `api → services → ai_agents → core`. Never import `app.api` from `services/`.

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

CI enforces fractal docs, no-stub guards on `api/` and `channels/providers/`, and the line-budget gate on pull requests.

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
