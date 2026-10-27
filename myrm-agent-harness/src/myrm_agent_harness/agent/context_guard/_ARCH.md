# Context Guard and Transparent Spillover Architecture

[INPUT]
- `myrm_agent_harness.agent.context_guard.types`: SpilloverPayload, SpilloverResult, ContextGuardConfig
- `pathlib.Path`: Filesystem path management
- `hashlib.sha256`: Integrity verification

[OUTPUT]
- `SpilloverEngine`: Engine for atomic, idempotent extraction of context bombs into workspace files; the stub it leaves shows the start and the end of the text.
- `EphemeralTransientSweeper`: 24-hour cleanup sweeper for transient spillover files.
- `TRANSIENT_SPILLOVER_DIR` / `KEPT_SPILLOVER_DIR`: the two spill lifetimes (`.myrm/spillover` swept after 24 h, `.myrm/pastes` never swept).

[POS]
Harness-level context safety subsystem preventing LLM context window explosions
by gracefully converting oversized payloads (>16,000 chars) into referenced files.

## Design Notes

- **Two lifetimes, one engine.** A spill nothing refers to after the turn (a document a messaging channel attached) goes to
  the transient directory and is swept. The text a person pasted is referred to by the conversation for as long as it lasts
  (the agent thread replays the stub of the first turn), so it goes to the kept directory, which has no sweeper: the owner of
  the workspace deletes it. The Fast-mode `file_read_tool` scope reads both names from `types.py`, so the writer and the
  reader cannot drift apart.
- **The stub is a pure function of the text.** The file is named after the content hash, the write is skipped when the same
  bytes are already there, and the stub carries no per-call data (no session id, no timestamp). A live turn and a stored
  conversation therefore render the same bytes and name the same file.
- **The stub shows both ends.** A person often types the question after the pasted material; a head-only preview would hide
  it. The instruction says the pasted text is the request when nothing else is in the message.
- **Not Vault / UECD.** Those stores serve tool output of a run; a paste belongs to the conversation and must stay readable
  at a path the stored message names, without a store lookup.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Public re-exports for the context guard engine, sweeper, and config/payload types. | ✅ |
| types.py | Core | Context guard data models (`ContextGuardConfig`, `SpilloverPayload`, `SpilloverResult`), the two spill directory names and `estimate_token_pressure`. | ✅ |
| spillover_engine.py | Core | `SpilloverEngine` — atomic, content-addressed extraction of context bombs into workspace files; renders the byte-stable stub (start and end preview, relative path, digest). | ✅ |
| sweeper.py | Core | `EphemeralTransientSweeper` — 24-hour cleanup sweeper for transient spillover files. | ✅ |
