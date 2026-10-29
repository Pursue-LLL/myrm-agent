# workspace_rules/

## Overview
Workspace rules — project-level context file discovery and injection.

Two-layer mechanism:
1. **Workspace context injection** (`middleware.py`): On every model call, reads the workspace rules live and injects them, with the sandbox snapshot, as one SystemMessage after `user_instructions`, before `memory_context`. The snapshot is taken once per chat thread (`before_model`) and kept in private checkpointed state.
2. **Progressive discovery** (`tracker.py`): Monitors tool call arguments for directory paths, discovers rules in newly accessed subdirectories, appends to tool results.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Public API exports for workspace rules module. | — |
| adr_scanner.py | Core | Architectural Decision Record (ADR) scanner. Discovers MADR format decisions under docs/decisions/ and filters by status (keeps accepted/active, filters out deprecated/superseded). | ✅ |
| scanner.py | Core | Rule file discovery, security scanning, YAML frontmatter stripping, and loading. Uses First-Match-Wins priority loading per directory to prevent conflicts (e.g., .myrm.md > SOUL.md > MEMORY.md > AGENTS.md > .cursorrules). Supports AGENTS.md, CLAUDE.md, SOUL.md, MEMORY.md, KNOWN_ISSUES.md, docs/decisions/*.md, .cursorrules, .clinerules, .myrm.md, .hermes.md, HERMES.md, .windsurfrules, .myrm/rules/*.md, .cursor/rules/*.mdc, .claude/CLAUDE.md, .github/copilot-instructions.md. Traverses upward to git root (max 5 levels). inode-level dedup for case-insensitive filesystems. Head/tail truncation for large files. Blocked files (injection detected: unambiguous `block_score` ≥ 0.8, so ordinary role/mode phrasing does not block) return a `[BLOCKED]` placeholder RuleFile with `blocked=True` instead of being silently skipped. | ✅ |
| middleware.py | Core | AgentMiddleware for workspace context injection. Injects discovered rules and lightweight sandbox environment bootstrap snapshot (working dir, entries, runtimes, package managers) as SystemMessage at KV Cache-optimal position (after user_instructions, before memory_context). Rules are read live on every call; the snapshot is taken once per chat thread (`workspace_snapshot`, `workspace_snapshot_root` in private state, retaken when the workspace changes), so the text at this position does not move while the agent edits files. A workspace the trust gate blocks is neither probed nor injected. | ✅ |
| tracker.py | Core | SubdirectoryContextTracker for progressive rule discovery. Session-scoped via ContextVar. Extracts directory paths from tool call arguments, checks for rule files, appends content to tool results (not system prompt). Enforces 16000 char budget with explicit truncation to prevent silent dropping. Integrated via tool_interceptor_middleware POST-CALL stage. | ✅ |

## Key Dependencies

- `agent.security.detection.prompt_guard` — injection pattern scanning
- `agent.security.detection.content_boundary` — Unicode sanitization, marker neutralization
- `agent.middlewares._session_context` — workspace_root ContextVar
- `agent.middlewares.tooling.tool_interceptor_middleware` — POST-CALL integration for tracker
