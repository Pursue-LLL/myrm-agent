# cli/

## Overview
CLI runtime backend — spawns one external CLI agent process per turn (Claude Code, Codex, ...) and streams its NDJSON output as `RuntimeEvent`s. Session continuity between turns rides on the CLI's own session id (`--resume`); the id is kept by `CliSessionBook`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade: lazy `CliRuntime`. The other modules are imported by their own path. | ✅ |
| parser.py | Internal | Shared NDJSON event parsers for CLI runtimes, including the whole-line entry `parse_ndjson_line` (Claude stream-json, Codex item.* and legacy envelope, plain text). | ✅ |
| runtime.py | Core | `CliRuntime`: spawns a CLI agent process, resolves launch and permission-mode args via the auth profile registry, and parses NDJSON output. Resumes the session the CLI reported (`--resume`, only when started in the directory that created it); an optional `CliSessionStore` carries the id across host restarts. | ✅ |
| session.py | Core | `CliSessionBook`: bounded memory-first CLI session records with best-effort write-through to the host `CliSessionStore` (contract and `CliSessionRecord` live in `types.py`); store failures degrade to a fresh session and never fail a turn. | ✅ |
| spawn_hints.py | Internal | Bare CLI spawn failure hints for CliRuntime error messages. | ✅ |
