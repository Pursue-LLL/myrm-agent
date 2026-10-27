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

- **The limits are the caller's.** The `ContextGuardConfig` defaults (16,000 chars, token pressure 8,000) suit third-party text. A caller that
  parks the text of a person passes higher limits of its own, and a caller that copies a parked file to another workspace uses an engine
  with zero limits, so that the copy does not depend on the limit the text was parked under.
- **The estimate weighs each character by its kind.** `estimate_token_pressure` is a proxy for the real token count, and
  what matters is how far it can fall below it: a text that costs twice what the estimate says passes a limit set for prose.
  Lowercase letters and white space weigh 0.25, capitals 1, digits 0.75, other ASCII 0.4, non-ASCII narrow characters 0.5 and
  East Asian wide characters 1.8, as whole hundredths so the web composer (`spillover.ts`) sums to the same number. Against
  tiktoken `o200k_base` the recorded samples (prose, code, logs, URLs, minified JSON, hex, base64, seven scripts) stay within
  0.4x-1.3x of the real count (`tests/agent/context_guard/test_token_pressure.py`). The cost of the weights: ALL CAPS and
  Title Case prose are over-estimated by 2-3x, Chinese by 2.25x and Japanese by 1.9x (1.8 per wide character against the
  0.8-0.95 o200k measures, kept high because other tokenizers split CJK finer), so these park earlier than their token
  count calls for. A text parked early costs one file read; a text that slips past costs its tokens on every replayed turn.
- **The estimate is not `get_token_count`.** `utils.text_utils.get_token_count` is exact for o200k, but it downloads its BPE
  data on first use and, when tiktoken fails, silently returns `estimate_tokens_fast` (50,000 characters of the log recipe in
  the contract test: 23,837 with tiktoken, 14,285 without, across a 16,000 limit). The live turn and the stored message each
  decide on their own, so a decision that depends on that state would park the text in one and keep it in the other, and the
  stub would no longer be the same bytes in both. The estimate stays a pure function of the text. It is also 3-9x faster on
  dense and adversarial input (64,000 base64 characters 1.6 ms against 5.2 ms, a million `a` 19.3 ms against 175.5 ms), and
  the web composer has no tokenizer to call.
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
| types.py | Core | Context guard data models (`ContextGuardConfig`, `SpilloverPayload`, `SpilloverResult`), the two spill directory names and `estimate_token_pressure` (weights per kind of character). | ✅ |
| spillover_engine.py | Core | `SpilloverEngine` — atomic, content-addressed extraction of context bombs into workspace files; renders the byte-stable stub (start and end preview, relative path, digest). | ✅ |
| sweeper.py | Core | `EphemeralTransientSweeper` — 24-hour cleanup sweeper for transient spillover files. | ✅ |
