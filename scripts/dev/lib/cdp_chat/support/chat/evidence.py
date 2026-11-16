"""Evidence in stored chat messages.

[INPUT]
- cdp_chat.support.api_client::_E2E_API_REQUEST_ATTEMPTS (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.chat.session::fetch_chat_messages (POS: Chat session calls of the E2E over the REST API: create, cancel, read messages, steer)

[OUTPUT]
- file_write_tool_call_count, file_write_tool_invoked_in_messages, empty_write_failure_in_messages: whether the file-write tool ran and whether it failed with empty content
- chat_user_message_count, chat_messages_have_ok, chat_messages_have_done: what the stored messages show of a turn
- stored_reply_matches: whether enough user messages are stored and the newest assistant reply matches a pattern (the test every reply check shares)
- wait_chat_messages_done: poll until the newest assistant reply says DONE

[POS]
What the stored chat messages prove about a turn: a real file-write tool call, an OK or DONE reply in the newest assistant message, the user message count. Evidence comes from persisted messages, never from the prompt text.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
from collections.abc import Callable, Sequence

from cdp_chat.support.api_client import _E2E_API_REQUEST_ATTEMPTS
from cdp_chat.support.chat.session import fetch_chat_messages

_DONE_REPLY_RE = re.compile(r"\bDONE\b", re.IGNORECASE)
_AGENT_TURN_DONE_RE = re.compile(r"(?:\bOK\b|GOAL_OK|\bDONE\b)", re.IGNORECASE)

FILE_WRITE_TOOL_E2E_NAME = "file_write_tool"
EMPTY_FILE_WRITE_ERROR = "Cannot write empty file content"


def _structured_tool_name(call: dict[str, object]) -> str:
    fn = call.get("function")
    return str(
        call.get("name") or (fn.get("name") if isinstance(fn, dict) else "") or ""
    )


def file_write_tool_call_count(
    chat_id: str,
    *,
    api_url: str | None = None,
    tool_name: str = FILE_WRITE_TOOL_E2E_NAME,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> int:
    count = 0
    for msg in fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    ):
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if isinstance(call, dict) and _structured_tool_name(call) == tool_name:
                    count += 1
        if str(msg.get("role") or "") == "tool":
            name = str(msg.get("name") or msg.get("tool_name") or "")
            if name == tool_name:
                count += 1
    return count


def file_write_tool_invoked_in_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
    tool_name: str = FILE_WRITE_TOOL_E2E_NAME,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> bool:
    """SSOT: real tool invoke from assistant/tool messages — never user prompt text."""
    return (
        file_write_tool_call_count(
            chat_id,
            api_url=api_url,
            tool_name=tool_name,
            timeout_sec=timeout_sec,
            max_attempts=max_attempts,
        )
        >= 1
    )


def empty_write_failure_in_messages(
    chat_id: str,
    *,
    api_url: str | None = None,
    tool_name: str = FILE_WRITE_TOOL_E2E_NAME,
    empty_error: str = EMPTY_FILE_WRITE_ERROR,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> tuple[bool, bool]:
    tool_invoked = file_write_tool_invoked_in_messages(
        chat_id,
        api_url=api_url,
        tool_name=tool_name,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    has_mutation_failure = False
    for msg in fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    ):
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        blob = json.dumps(msg, ensure_ascii=False, default=str)
        failures = msg.get("fileMutationFailures")
        if not isinstance(failures, list):
            meta = msg.get("metadata")
            if isinstance(meta, dict):
                failures = meta.get("fileMutationFailures")
                steps = meta.get("progressSteps")
                if isinstance(steps, list):
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        if step.get("type") == "file_mutation_failed":
                            has_mutation_failure = True
                        detail = json.dumps(step, ensure_ascii=False, default=str)
                        if empty_error in detail:
                            has_mutation_failure = True
        if isinstance(failures, list) and failures:
            for row in failures:
                if not isinstance(row, dict):
                    continue
                preview = str(row.get("error_preview") or "")
                if empty_error in preview:
                    has_mutation_failure = True
        if role != "user" and empty_error in blob:
            has_mutation_failure = True
    if has_mutation_failure:
        tool_invoked = True
    return tool_invoked, has_mutation_failure


def chat_user_message_count(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> int:
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    return _user_message_count(messages)


def _user_message_count(messages: Sequence[object]) -> int:
    return sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )


def _newest_assistant_content(messages: Sequence[object]) -> str | None:
    """Text of the newest assistant message; None when the chat has no assistant message."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            return str(msg.get("content") or "")
    return None


def stored_reply_matches(
    messages: Sequence[object], pattern: re.Pattern[str], *, min_user_count: int
) -> bool:
    """True when at least `min_user_count` user messages are stored and the newest assistant reply matches."""
    if _user_message_count(messages) < min_user_count:
        return False
    reply = _newest_assistant_content(messages)
    return reply is not None and pattern.search(reply) is not None


def chat_messages_have_ok(
    chat_id: str,
    *,
    min_user_count: int = 1,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
    max_attempts: int = _E2E_API_REQUEST_ATTEMPTS,
) -> bool:
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    return stored_reply_matches(
        messages, _AGENT_TURN_DONE_RE, min_user_count=min_user_count
    )


def chat_messages_have_done(
    chat_id: str,
    *,
    min_user_count: int = 1,
    api_url: str | None = None,
    timeout_sec: float = 15.0,
) -> bool:
    messages = fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=timeout_sec,
    )
    return stored_reply_matches(messages, _DONE_REPLY_RE, min_user_count=min_user_count)


def wait_chat_messages_done(
    chat_id: str,
    *,
    api_url: str | None = None,
    timeout_sec: float = 120.0,
    fetch_timeout_sec: float = 15.0,
    progress_interval_sec: float = 30.0,
    on_tick: Callable[[], None] | None = None,
) -> bool:
    """Poll chat REST until assistant DONE or timeout (STREAM_CONVERGE SSOT)."""
    deadline = time.monotonic() + timeout_sec
    last_progress_at = time.monotonic()
    while time.monotonic() < deadline:
        if on_tick is not None:
            on_tick()
        try:
            if chat_messages_have_done(
                chat_id,
                api_url=api_url,
                timeout_sec=fetch_timeout_sec,
            ):
                return True
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            print(
                f"E2E_WAIT_API_DONE_SKIP: transient messages poll — {exc!s:.120}",
                flush=True,
            )
        now = time.monotonic()
        if now - last_progress_at >= progress_interval_sec:
            try:
                messages = fetch_chat_messages(
                    chat_id,
                    api_url=api_url,
                    timeout_sec=fetch_timeout_sec,
                )
                # Leading slice, not a tail: the DONE gate matches the literal word
                # at the start of the newest assistant reply, so the head is what an
                # operator needs to see.
                assistant_head = (_newest_assistant_content(messages) or "")[:80]
                print(
                    f"E2E_WAIT_API_DONE_PROGRESS: chatId={chat_id} "
                    f"messages={len(messages)} assistant_head={assistant_head!r} "
                    f"remaining={int(deadline - now)}s",
                    flush=True,
                )
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                print(
                    f"E2E_WAIT_API_DONE_PROGRESS_SKIP: {exc!s:.120}",
                    flush=True,
                )
            last_progress_at = now
        time.sleep(2.0)
    return False
