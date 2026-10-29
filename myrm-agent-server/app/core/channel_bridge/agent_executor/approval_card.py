"""The approval card a channel turn shows when a tool waits for the member's decision.

[INPUT]
- app.channels.i18n::channel_t (POS: catalog message in the sender's language)
- app.channels.types::ApprovalExpiry, ProgressUpdate, QuickReply (POS: card text, buttons and the wait's time limit)
- myrm_agent_harness.utils.coercion::parse_float (POS: tolerant numeric parsing)

[OUTPUT]
- build_approval_card: harness ``tool_approval_request`` payload + locale + the run's session key → ProgressUpdate

[POS]
Turns the harness approval payload into the card the chat shows: what needs approval, how long the wait lasts and what
the timeout decides, plus the answer buttons. The wording and the buttons come from the channel catalog in the sender's
language; tool names are shown as they are. A reason the harness coded is worded from the catalog too, and one it
did not code is shown as written. The time limit also travels as
``ProgressUpdate.expiry`` so the router times the wait out with the same number the card states, and the session of the
asking run as ``ProgressUpdate.session_key`` so the answer resumes that session's chat.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.utils.coercion import parse_float

from app.channels.i18n import channel_t
from app.channels.types import ApprovalExpiry, ProgressUpdate, QuickReply

_DEFAULT_TIMEOUT_SECONDS = 300.0


def build_approval_card(data: dict[str, object], *, locale: str, session_key: str) -> ProgressUpdate:
    """The card for one approval request (a single tool or a batch), worded for ``locale``, of the run in ``session_key``."""
    action_requests = data.get("actionRequests", [])
    extensions = data.get("extensions", {})
    timeout_info = extensions.get("timeout", {}) if isinstance(extensions, dict) else {}
    if not isinstance(timeout_info, dict):
        timeout_info = {}
    seconds = parse_float(timeout_info.get("seconds", _DEFAULT_TIMEOUT_SECONDS), _DEFAULT_TIMEOUT_SECONDS)
    behavior: Literal["deny", "allow"] = "allow" if timeout_info.get("behavior", "deny") == "allow" else "deny"

    if isinstance(action_requests, list) and action_requests:
        tool_names = [str(req.get("action", "unknown")) for req in action_requests if isinstance(req, dict)]
        reasons = [_reason_text(req, locale) for req in action_requests if isinstance(req, dict)]
        tools = ", ".join(tool_names) if tool_names else "unknown"
        reason = "; ".join(text for text in reasons if text)
    else:
        tools = str(data.get("tool_name", "unknown"))
        reason = str(data.get("reason", ""))

    request_line = (
        channel_t(locale, "approval_request", tools=tools, reason=reason)
        if reason
        else channel_t(locale, "approval_request_no_reason", tools=tools)
    )
    timeout_key = "approval_timeout_line_allow" if behavior == "allow" else "approval_timeout_line_deny"
    lines = [request_line, channel_t(locale, timeout_key, seconds=str(int(seconds)))]
    if _security_reviewer_recommends_denial(data):
        lines[0] = f"{channel_t(locale, 'approval_security_recommends_denial')} {lines[0]}"

    batch_size = len(action_requests) if isinstance(action_requests, list) else 0
    return ProgressUpdate(
        label="\n".join(lines),
        quick_replies=_answer_buttons(locale, batch_size),
        expiry=ApprovalExpiry(seconds=seconds, behavior=behavior),
        session_key=session_key,
    )


def _reason_text(request: dict[str, object], locale: str) -> str:
    """One request's reason in ``locale`` when the harness coded it and the catalog words that code, else as written."""
    code = request.get("reasonCode")
    if isinstance(code, str):
        key = f"approval_reason_{code}"
        worded = str(channel_t(locale, key, subject=str(request.get("reasonSubject") or "")))
        if worded != key:
            return worded
    return str(request.get("description") or "")


def _security_reviewer_recommends_denial(data: dict[str, object]) -> bool:
    review_configs = data.get("reviewConfigs", [])
    return isinstance(review_configs, list) and any(
        isinstance(rc, dict) and rc.get("smartDenied") is True for rc in review_configs
    )


def _answer_buttons(locale: str, batch_size: int) -> tuple[QuickReply, ...]:
    """Approve / deny; a batch adds the per-tool answer (``/batch a,a,..``) and words the first two for all of them."""
    if batch_size <= 1:
        return (
            QuickReply(label=channel_t(locale, "approval_button_approve"), text="/approve", required=True),
            QuickReply(label=channel_t(locale, "approval_button_deny"), text="/deny", required=True),
        )
    return (
        QuickReply(label=channel_t(locale, "approval_button_approve_all"), text="/approve", required=True),
        QuickReply(label=channel_t(locale, "approval_button_deny_all"), text="/deny", required=True),
        QuickReply(
            label=channel_t(locale, "approval_button_batch"),
            text=f"/batch {','.join('a' for _ in range(batch_size))}",
            required=True,
        ),
    )
