# acp/

## Overview
ACP runtime backend — keeps one external ACP-compatible agent process per backend (Claude Code, Codex CLI, ...) and drives it over the ACP JSON-RPC protocol on stdin/stdout: session reuse, resume, cancel, permission requests, file access with path safety, image prompts, and a bounded stop for an agent that stopped reading.

Detailed design: [ACP_SYSTEM.md](../../ACP_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade: lazy `AcpRuntime`. The other modules are imported by their own path. | ✅ |
| callback.py | Core | ACP callback handler for the AcpRuntime backend. | ✅ |
| runtime.py | Core | ACP protocol runtime backend — session reuse, cancel, resume; a prompt failure re-raises to surface as ERROR once the turn's events have been consumed to the end, and is only logged at INFO (`acp_prompt_task_failed_after_close`) when the consumer closed the turn first (a stop that ended the agent), so closing never turns into an error; `session/close` is sent only when `initialize` advertised `sessionCapabilities.close` and is bounded (4s), so a silent agent cannot skip the transport teardown that terminates its process; an agent that stays silent is reported as `working` every `KEEPALIVE_SECONDS`, and a missing ACP SDK (the optional `acp` extra) ends the turn with one named `BACKEND_NOT_FOUND` error that says how to install it. Turn images are sent as ACP image content blocks after the text block, only when `initialize` advertised `promptCapabilities.image` (an agent without it gets the text alone, an INFO log and an `images_not_sent` status update). A stop never waits for an agent that has stopped reading its stdin: `cancel` and the transport exit go through `stalled_agent`. | ✅ |
| stalled_agent.py | Internal | Bounded stop of an ACP agent that has stopped reading its stdin: a large prompt stuck in the pipe queues `session/cancel` and the SDK's transport exit behind itself, and the SDK's sender swallows the cancellation of a wait on it, so `cancel_session` and `leave_transport` wait at most `STALLED_AGENT_TIMEOUT_SECONDS` (5s) and then `end_agent` ends the agent and every process it started (the SDK spawns the agent in the host's own process group, which must not be signalled, so `code_execution/session/process_tree.py` walks the tree process by process). Releasing the agent's pipes is what fails the stuck write and frees the queue; ending the agent alone would leave its tools running and, when one inherited the agent's stdin, the write stuck. A healthy agent never reaches the bound. | ✅ |
