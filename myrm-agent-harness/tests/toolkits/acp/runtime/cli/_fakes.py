"""Test doubles shared by the CLI runtime tests: an in-memory session store and a scripted stand-in for the CLIs."""

from __future__ import annotations

import json
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.toolkits.acp.runtime.cli.runtime import CliRuntime
from myrm_agent_harness.toolkits.acp.types import (
    CliSessionRecord,
    CliSessionStore,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
)


class RecordingStore:
    """In-memory ``CliSessionStore`` that logs every operation and can be told to fail one."""

    def __init__(self) -> None:
        self.records: dict[str, CliSessionRecord] = {}
        self.ops: list[tuple[str, str]] = []
        self.failing: set[str] = set()

    async def load(self, session_id: str) -> CliSessionRecord | None:
        self._enter("load", session_id)
        return self.records.get(session_id)

    async def save(self, session_id: str, record: CliSessionRecord) -> None:
        self._enter("save", session_id)
        self.records[session_id] = record

    def _enter(self, op: str, session_id: str) -> None:
        self.ops.append((op, session_id))
        if op in self.failing:
            raise RuntimeError(f"{op} failed")


# A POSIX script standing in for the CLI agents. It behaves as the real binaries do (verified against claude 2.1.x
# and codex 0.164): a new conversation announces its id first (Claude ``system/init``, Codex ``thread.started``) and
# is only found again from the directory that created it; resuming an unknown id fails fast without announcing
# anything; one failing turn can end in a max-turns / API-error ``result`` line. Which command it plays is decided by
# its own file name; scenario.json next to it picks what a turn does (one dict for every call, or a list by call index).
_SCRIPT = """\
#!__PYTHON__
import json, os, signal, sys, time, uuid

here = os.path.dirname(os.path.abspath(__file__))
name = os.path.basename(sys.argv[0])
argv = sys.argv[1:]
cwd = os.getcwd()


def read_json(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


calls_path = os.path.join(here, "calls.jsonl")
index = len(open(calls_path).readlines()) if os.path.exists(calls_path) else 0
scenario = read_json(os.path.join(here, "scenario.json"), {})
if isinstance(scenario, list):
    scenario = scenario[min(index, len(scenario) - 1)]

prompt = sys.stdin.read() if "-p" in argv else (argv[-1] if argv else "")
with open(calls_path, "a") as handle:
    handle.write(json.dumps({"name": name, "argv": argv, "cwd": cwd, "prompt": prompt, "env": dict(os.environ)}) + "\\n")

if scenario.get("ignore_sigterm"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if scenario.get("exit_on_sigterm"):
    # The real claude traps SIGTERM and exits with 143, a positive code, rather than dying by the signal.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(scenario["exit_on_sigterm"]))


def emit(obj):
    print(obj if isinstance(obj, str) else json.dumps(obj), flush=True)


def finish(code=0):
    if scenario.get("stderr"):
        sys.stderr.write(scenario["stderr"] + "\\n")
    sys.exit(scenario.get("exit", code))


def hang_if(key):
    if scenario.get(key):
        time.sleep(120)


disk = os.path.join(here, "conversations.json")
known = read_json(disk, [])


def register(conversation):
    known.append(conversation)
    json.dump(known, open(disk, "w"))


hang_if("hang_before_output")
if scenario.get("fail_before_output"):
    finish(1)
if scenario.get("big_line"):
    emit({"type": "assistant", "content": "x" * scenario["big_line"]})

if name == "claude":
    resume = argv[argv.index("--resume") + 1] if "--resume" in argv else None
    if resume is not None and {"id": resume, "cwd": cwd} not in known:
        message = "No conversation found with session ID: " + resume
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "session_id": resume,
              "terminal_reason": "aborted_streaming", "errors": [message]})
        sys.stderr.write(message + "\\n")
        sys.exit(1)
    session_id = resume or str(uuid.uuid4())
    if resume is None:
        register({"id": session_id, "cwd": cwd})
    emit({"type": "system", "subtype": "init", "session_id": session_id, "cwd": cwd})
    hang_if("hang_after_init")
    time.sleep(scenario.get("silent_seconds", 0))
    text = scenario.get("text", session_id)
    for number in range(scenario.get("tools", 0)):
        call = {"type": "tool_use", "id": "toolu_%d" % number, "name": "Bash", "input": {"command": "echo %d" % number}}
        emit({"type": "assistant", "message": {"id": "msg_t%d" % number, "content": [call]}})
        result = {"type": "tool_result", "tool_use_id": "toolu_%d" % number, "content": "out %d" % number}
        emit({"type": "user", "message": {"content": [result]}})
    if "--include-partial-messages" in argv and scenario.get("partial"):
        start = {"type": "message_start", "message": {"id": "msg_1"}}
        emit({"type": "stream_event", "api_message_id": "msg_1", "event": start})
        for piece in (text[: len(text) // 2], text[len(text) // 2 :]):
            delta = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": piece}}
            emit({"type": "stream_event", "api_message_id": "msg_1", "event": delta})
    if text:
        emit({"type": "assistant", "message": {"id": "msg_1", "content": [{"type": "text", "text": text}]}})
    fail = scenario.get("fail")
    if fail == "max_turns":
        emit({"type": "result", "subtype": "error_max_turns", "is_error": True, "terminal_reason": "max_turns",
              "errors": ["Reached maximum number of turns (3)"], "session_id": session_id})
        finish(1)
    if fail == "api_error":
        notice = {"id": "msg_err", "model": "<synthetic>", "content": [{"type": "text", "text": "API Error: 400 bad"}]}
        emit({"type": "assistant", "error": "invalid_request", "message": notice})
        emit({"type": "result", "subtype": "success", "is_error": True, "result": "API Error: 400 bad",
              "api_error_status": 400, "terminal_reason": "api_error", "session_id": session_id})
        finish(1)
    if fail == "not_logged_in":
        # Nobody is logged in: no API call is made, so the result has no status, only the error category.
        text = "Not logged in \\u00b7 Please run /login"
        notice = {"id": "msg_err", "model": "<synthetic>", "content": [{"type": "text", "text": text}]}
        emit({"type": "assistant", "error": "authentication_failed", "message": notice})
        emit({"type": "result", "subtype": "success", "is_error": True, "result": text,
              "api_error_status": None, "session_id": session_id})
        finish(1)
    hang_if("hang_after_text")
    if fail == "crash":
        finish(3)
    usage = {"input_tokens": 10, "output_tokens": 5}
    emit({"type": "result", "subtype": "success", "is_error": False, "result": text, "usage": usage,
          "terminal_reason": "completed", "session_id": session_id})
    finish(0)

elif name == "codex":
    resuming = "exec" in argv and "resume" in argv[argv.index("exec") + 1 :]
    thread = argv[-2] if resuming else str(uuid.uuid4())
    if resuming and {"id": thread, "cwd": "*"} not in known:
        sys.stderr.write("Error: thread/resume: no rollout found for thread id " + thread + "\\n")
        sys.exit(1)
    if not resuming:
        register({"id": thread, "cwd": "*"})
    emit({"type": "thread.started", "thread_id": thread})
    emit({"type": "turn.started"})
    hang_if("hang_after_init")
    for number in range(scenario.get("retry_notices", 0)):
        # Codex reports every retry of a request as an error line; the turn can still succeed afterwards.
        emit({"type": "error", "message": "Reconnecting... %d/5 (stream disconnected)" % (number + 1)})
    fail = scenario.get("fail")
    if fail == "auth":
        denied = "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header"
        emit({"type": "error", "message": "Reconnecting... 1/5 (" + denied + ")"})
        emit({"type": "error", "message": denied})
        emit({"type": "turn.failed", "error": {"message": denied}})
        finish(1)
    if fail == "error_line_only":
        emit({"type": "error", "message": "model not supported"})
        finish(1)
    if fail == "turn_failed":
        emit({"type": "turn.failed", "error": {"message": "stream disconnected"}})
        finish(1)
    text = scenario.get("text", thread)
    emit({"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": text}})
    emit({"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 3}})
    finish(0)

else:
    hang_if("hang_after_init")
    emit({"type": "assistant", "content": scenario.get("text", "ok")})
    finish(0)
"""


@dataclass
class FakeCli:
    """The scripted CLI stand-ins of one test, plus the log of how they were invoked."""

    bin_dir: Path

    def command(self, name: str = "claude") -> Path:
        """The executable that plays ``name``; its file name decides which CLI it imitates."""
        path = self.bin_dir / name
        if not path.exists():
            path.write_text(_SCRIPT.replace("__PYTHON__", sys.executable))
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    def set_scenario(self, scenario: dict[str, object] | list[dict[str, object]]) -> None:
        (self.bin_dir / "scenario.json").write_text(json.dumps(scenario))

    def calls(self, name: str | None = None) -> list[dict[str, object]]:
        path = self.bin_dir / "calls.jsonl"
        if not path.exists():
            return []
        calls = [json.loads(line) for line in path.read_text().splitlines()]
        return [call for call in calls if name is None or call["name"] == name]

    def resume_args(self, name: str = "claude") -> list[str | None]:
        """The CLI session id each call asked to resume (None for a fresh session)."""
        resumed: list[str | None] = []
        for call in self.calls(name):
            argv = call["argv"]
            assert isinstance(argv, list)
            if name == "claude":
                resumed.append(argv[argv.index("--resume") + 1] if "--resume" in argv else None)
            else:
                exec_index = argv.index("exec") if "exec" in argv else -1
                is_resume = exec_index >= 0 and "resume" in argv[exec_index + 1 :]
                resumed.append(argv[-2] if is_resume else None)
        return resumed


def make_runtime(
    fake_cli: FakeCli,
    name: str = "claude",
    *,
    store: CliSessionStore | None = None,
    **overrides: object,
) -> CliRuntime:
    """A ``CliRuntime`` for the stand-in that plays ``name``; ``overrides`` replace ``RuntimeConfig`` fields."""
    settings: dict[str, object] = {
        "backend_type": "cli",
        "command": str(fake_cli.command(name)),
        "args": ["-p", "--output-format", "stream-json"] if name == "claude" else [],
        "permission_mode": "safe",
        "cwd": str(fake_cli.bin_dir.parent),
        "timeout_seconds": 20,
    }
    settings.update(overrides)
    return CliRuntime(name, RuntimeConfig(**settings), session_store=store)  # type: ignore[arg-type]


async def run_turn(runtime: CliRuntime, prompt: str = "hello", session_id: str = "s1") -> list[RuntimeEvent]:
    return [event async for event in runtime.run_turn(prompt, session_id)]


def types_of(events: list[RuntimeEvent]) -> list[RuntimeEventType]:
    return [event.type for event in events]


def text_of(events: list[RuntimeEvent]) -> str:
    return "".join(str(e.data["content"]) for e in events if e.type == RuntimeEventType.TEXT_DELTA)


def errors_of(events: list[RuntimeEvent]) -> list[RuntimeEvent]:
    return [event for event in events if event.type == RuntimeEventType.ERROR]


def statuses_of(events: list[RuntimeEvent]) -> list[str]:
    return [str(e.data["status"]) for e in events if e.type == RuntimeEventType.STATUS_UPDATE]
