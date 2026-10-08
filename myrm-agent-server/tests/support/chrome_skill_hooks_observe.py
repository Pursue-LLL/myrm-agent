"""Chrome LIVE E2E support: what a live skill-hooks turn left behind.

[INPUT]
- cdp_chat.support (POS: chat transcript fetch, private backend log location)
- tests.support.chrome_skill_hooks_live_e2e (POS: SkillChat probe, the words the probe turns agree on)

[OUTPUT]
- wait_user_message_persisted() / wait_assistant_reply_ending_with() / transcript_text(): the chat as stored
- read_json() / wait_for_file() / assert_no_hook_raised(): the hooks' side effects and the backend log
- assert_audit_turn_governed(): the evidence a bash turn under ``audit_hooks`` must have left

[POS]
Shared by tests/e2e/test_skill_hooks_live_chrome_e2e.py. Hook side effects (files written by the hooks, not by the
model) are the evidence that the product path wired the skill's hooks into the live turn.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import backend_log_path, fetch_chat_messages  # noqa: E402

from tests.support.chrome_skill_hooks_live_e2e import BASH_TOOL, COMMAND_OUTPUT, SkillChat  # noqa: E402


def _message_text(content: object) -> str:
    """A stored message's words: plain text, or the text blocks of a message that carries attachments."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = [block.get("text") for block in content if isinstance(block, dict)]
        return "\n".join(text for text in blocks if isinstance(text, str))
    return ""


def _stored_as_sent(text: str, wire: str, *, exact: bool, spilled: bool) -> bool:
    if spilled:
        invocation = parse_use_tag(wire)
        return invocation is not None and text.startswith(invocation.tag) and "<file_spillover" in text
    return text == wire if exact else wire in text


def wait_user_message_persisted(
    chat_id: str,
    api_url: str,
    wire: str,
    *,
    exact: bool = True,
    spilled: bool = False,
    timeout_sec: float = 60.0,
) -> None:
    """The server stored the user turn as the composer sent it, ``[use skill]`` tag included.

    ``exact=False`` for a turn with attachments, whose stored message holds more than the typed words.
    ``spilled=True`` for a message over the Context Guard's cap: it is stored as a reference to the file it was
    spilled into, with the tag still in front.
    """
    deadline = time.monotonic() + timeout_sec
    stored: list[str] = []
    fetch_error = "none"
    while time.monotonic() < deadline:
        try:
            stored = [
                _message_text(message.get("content"))
                for message in fetch_chat_messages(chat_id, api_url=api_url)
                if isinstance(message, dict) and message.get("role") == "user"
            ]
            fetch_error = "none"
        except OSError as exc:
            stored = []
            fetch_error = f"{type(exc).__name__}: {exc}"
        if any(_stored_as_sent(text, wire, exact=exact, spilled=spilled) for text in stored):
            return
        time.sleep(1.0)
    pytest.fail(
        f"server never stored the composer's wire message {wire[:300]!r} ({len(wire)} chars); "
        f"user messages={[text[:300] for text in stored]!r}; "
        f"last fetch error: {fetch_error}\n{describe_backend(api_url, chat_id)}\n"
        f"--- backend log excerpt ---\n{backend_log_excerpt(api_url)}"
    )


def describe_backend(api_url: str, chat_id: str) -> str:
    """Whether the private backend still answers and knows the chat.

    A dead or replaced backend reads as an empty chat, so a failed wait must say which one it was.
    """
    reports: list[str] = []
    for label, path in (("health", "/api/v1/health"), ("chat messages", f"/api/v1/chats/{chat_id}/messages")):
        try:
            with urllib.request.urlopen(f"{api_url.rstrip('/')}{path}", timeout=5.0) as response:  # noqa: S310 - loopback
                reports.append(f"{label}: HTTP {response.status} {response.read(240).decode('utf-8', 'replace')}")
        except urllib.error.HTTPError as exc:
            reports.append(f"{label}: HTTP {exc.code}")
        except OSError as exc:
            reports.append(f"{label}: {type(exc).__name__}: {exc}")
    return "backend probe: " + " | ".join(reports)


def _ends_with_token(content: str, token: str) -> bool:
    """The model was told to reply with exactly ``token``; a refusal that merely quotes it does not count."""
    return content.strip().rstrip("*`_.! ").endswith(token)


def wait_assistant_reply_ending_with(chat_id: str, api_url: str, token: str, *, timeout_sec: float) -> str:
    deadline = time.monotonic() + timeout_sec
    last_messages: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        last_messages = [m for m in messages if isinstance(m, dict)]
        for message in reversed(last_messages):
            content = message.get("content") or message.get("message") or ""
            if message.get("role") == "assistant" and isinstance(content, str) and _ends_with_token(content, token):
                print(f"E2E_ASSISTANT_REPLY[{chat_id}]: {content[:400]}", flush=True)
                return content
        time.sleep(2.0)
    pytest.fail(
        f"assistant reply ending with {token!r} not received within {timeout_sec}s; "
        f"messages={json.dumps(last_messages, ensure_ascii=False)[:1200]}"
    )


def transcript_text(chat_id: str, api_url: str) -> str:
    """The persisted chat messages (tool results included) as one searchable string."""
    return json.dumps(fetch_chat_messages(chat_id, api_url=api_url), ensure_ascii=False, default=str)


_LOG_TAIL_BYTES = 6_000_000
# Loggers that narrate how an explicit skill invocation becomes active hooks; the rest is noise.
_LOG_SOURCES = (
    "myrm_agent_harness.agent.skill_agent",
    "myrm_agent_harness.agent.hooks",
    "app.core.skills.loader",
    "app.ai_agents.general_agent.stream_pipeline",
)


def backend_log_excerpt(api_url: str, *, limit: int = 150) -> str:
    """Skill- and hook-related tail lines of the private backend's log, for failure messages."""
    path = backend_log_path(api_url)
    if not path.is_file():
        return f"(backend log not found: {path})"
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - _LOG_TAIL_BYTES))
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
    narration = [line[:400] for line in lines if any(f"🚀 {source}" in line for source in _LOG_SOURCES)]
    errors = [line[:400] for line in lines if " - ERROR - " in line]
    return "\n".join([*narration[-limit:], *errors[-10:]])


def _assert_hook_wrote(path: Path, *, api_url: str) -> None:
    """A missing file fails with what the backend logged about hooks and skills."""
    assert path.exists(), (
        f"hook did not write {path.name}; files={sorted(p.name for p in path.parent.iterdir())}\n"
        f"--- backend log excerpt ---\n{backend_log_excerpt(api_url)}"
    )


def assert_no_hook_raised(probe: SkillChat, api_url: str) -> None:
    """Hooks run inside the agent loop, which swallows a raising hook; only the backend log still shows it."""
    path = backend_log_path(api_url)
    with path.open("rb") as handle:
        handle.seek(probe.log_offset)
        lines = handle.read().decode("utf-8", errors="replace").splitlines()
    raised = [line[:400] for line in lines if "Hook [" in line and " raised: " in line]
    assert not raised, "a hook raised while the live turn ran:\n" + "\n".join(raised)


def read_json(path: Path, *, api_url: str) -> dict[str, object]:
    """The JSON a hook wrote."""
    _assert_hook_wrote(path, api_url=api_url)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), payload
    return payload


def wait_for_file(path: Path, *, api_url: str, timeout_sec: float = 30.0) -> None:
    """Block until a hook has written ``path``; a hook that never does fails the test."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline and not path.exists():
        time.sleep(0.5)
    _assert_hook_wrote(path, api_url=api_url)


def assert_audit_turn_governed(probe: SkillChat, api_url: str) -> None:
    """The ``audit_hooks`` of a turn that ran ``echo COMMAND_OUTPUT`` left the evidence of a governed run."""
    out = probe.out
    wait_for_file(out / "audit.log", api_url=api_url)

    # Activation: the explicit [use skill] invocation brought the SessionStart hook to life.
    session_payload = read_json(out / "session_payload.json", api_url=api_url)
    assert session_payload.get("session_id"), session_payload
    assert session_payload.get("is_resume") is False, session_payload

    # The tools: [bash_*] filter reached the live bash call, before and after it ran.
    pre = read_json(out / "pre_tool_payload.json", api_url=api_url)
    assert pre.get("tool_name") == BASH_TOOL, pre
    assert COMMAND_OUTPUT in json.dumps(pre.get("tool_input")), pre
    post = read_json(out / "post_tool_payload.json", api_url=api_url)
    assert post.get("tool_name") == BASH_TOOL, post
    assert COMMAND_OUTPUT in str(post.get("tool_output")), post  # the command really ran

    # SessionEnd ran inside the same turn; the gate-refused third-party hook never executed.
    assert (out / "audit.log").read_text(encoding="utf-8").splitlines() == ["ended"]
    assert not (out / "escalated.marker").exists()
    assert_no_hook_raised(probe, api_url)
