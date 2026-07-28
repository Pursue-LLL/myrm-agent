"""Browser takeover LIVE — backend API helpers (R98)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

_SSE_DONE_RE = re.compile(r"(?:\bOK\b|GOAL_OK|\bDONE\b)", re.IGNORECASE)


def cancel_chat_via_api(*, api_base: str, chat_id: str) -> bool:
    """Best-effort release of a stale gateway session before retrying a new chat."""
    url = (
        f"{api_base.rstrip('/')}/api/v1/agents/chats/"
        f"{urllib.parse.quote(chat_id, safe='')}/cancel"
    )
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True
        return False
    except (OSError, urllib.error.URLError):
        return False


def reset_hitl_runtime_via_api(*, api_base: str) -> bool:
    url = f"{api_base.rstrip('/')}/api/v1/security/allowlist/test/reset-hitl-runtime"
    req = urllib.request.Request(  # noqa: S310
        url,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        return False


def resume_via_api(
    *,
    api_base: str,
    chat_id: str,
    message_id: str,
    action: str = "completed",
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    """Resume agent via backend API and consume the SSE stream until completion."""
    url = f"{api_base.rstrip('/')}/api/v1/agents/agent-stream"
    payload = json.dumps(
        {
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "agent",
            "query": "",
            "resume_value": {"action": action, "message": ""},
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    collected_text = ""
    found_done = False
    re_interrupted = False
    resume_msg_id: str | None = None
    line_count = 0
    try:
        resp = urllib.request.urlopen(req, timeout=timeout_sec)  # noqa: S310
        if resp.status != 200:
            return {"ok": False, "error": f"HTTP {resp.status}"}
        print(f"E2E_RESUME_SSE: connected, status={resp.status}", flush=True)
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            line_count += 1
            if line_count <= 50 or line.startswith("data: "):
                print(f"E2E_RESUME_SSE: L{line_count}: {line[:200]}", flush=True)
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                print("E2E_RESUME_SSE: [DONE] sentinel", flush=True)
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                collected_text += data_str
                continue
            event_type = event.get("type", "")
            if event_type == "message":
                chunk = event.get("data", "")
                if isinstance(chunk, str):
                    collected_text += chunk
            elif event_type == "message_end":
                print(
                    f"E2E_RESUME_SSE: message_end after {line_count} lines", flush=True
                )
                completion_status = str(event.get("completion_status") or "").strip()
                if completion_status == "complete":
                    found_done = True
                break
            elif event_type == "error":
                error_data = event.get("data", "")
                status_code = event.get("status_code")
                error_type_name = str(event.get("error_type", ""))
                err_text = (
                    error_data
                    if isinstance(error_data, str)
                    else json.dumps(error_data, ensure_ascii=False)
                )
                if status_code == 409 or error_type_name == "AgentBusyError":
                    print(
                        f"E2E_RESUME_SSE: AgentBusyError at L{line_count} — "
                        f"{err_text[:120]}",
                        flush=True,
                    )
                    resp.close()
                    return {"ok": False, "error": f"HTTP 409: {err_text}"}
                print(
                    f"E2E_RESUME_SSE: error event at L{line_count} "
                    f"({error_type_name}): {err_text[:120]}",
                    flush=True,
                )
                resp.close()
                return {
                    "ok": False,
                    "error": f"SSE error ({error_type_name}): {err_text}",
                }
            elif event_type in ("approval_required", "browser_takeover_requested"):
                re_interrupted = True
                nested = event.get("data", {})
                if isinstance(nested, dict):
                    inner = nested.get("data")
                    inner_mid = (
                        inner.get("messageId") if isinstance(inner, dict) else None
                    )
                    resume_msg_id = nested.get("messageId") or inner_mid
                print(
                    f"E2E_RESUME_SSE: agent re-interrupted ({event_type}), "
                    f"resume_msg_id={resume_msg_id} — draining remaining SSE",
                    flush=True,
                )
            if not found_done and _SSE_DONE_RE.search(collected_text):
                found_done = True
                print(f"E2E_RESUME_SSE: DONE detected at L{line_count}", flush=True)
        resp.close()
        print(
            f"E2E_RESUME_SSE: stream ended, lines={line_count} "
            f"text_len={len(collected_text)} re_interrupted={re_interrupted}",
            flush=True,
        )
        if not found_done:
            found_done = bool(_SSE_DONE_RE.search(collected_text))
        return {
            "ok": True,
            "done": found_done,
            "re_interrupted": re_interrupted,
            "resume_msg_id": resume_msg_id,
            "text_sample": collected_text[:200],
        }
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode(errors="replace")
        print(f"E2E_RESUME_API: HTTP {exc.code} — {body}", flush=True)
        return {"ok": False, "error": f"HTTP {exc.code}: {body}"}
    except Exception as exc:
        if collected_text and _SSE_DONE_RE.search(collected_text):
            return {"ok": True, "done": True, "text_sample": collected_text[:200]}
        print(f"E2E_RESUME_API: {type(exc).__name__}: {exc}", flush=True)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
