"""Read what an in-page probe returned: result coercion and the blank-page and transport-error classifications."""

from __future__ import annotations

import json


def _coerce_evaluate_result(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"value": raw}


def _resolve_probe_pathname(last: dict[str, object]) -> str:
    pathname = str(last.get("pathname") or "").strip()
    if pathname:
        return pathname
    from urllib.parse import urlparse

    for key in ("url", "href"):
        raw = last.get(key)
        if isinstance(raw, str) and raw.strip():
            return urlparse(raw.strip()).path or ""
    return ""


def _state_looks_blank(last: dict[str, object]) -> bool:
    body_raw = last.get("bodyLength", last.get("bodyLen"))
    body_len = int(body_raw or 0) if body_raw is not None else 0
    if body_len == 0:
        return True
    if last.get("deferredLoading") is True and body_len < 80:
        return True
    if last.get("hasActiveSection") is False and int(last.get("matrixHits") or 0) == 0:
        heading = str(last.get("heading") or "")
        relay = str(last.get("relayLine") or "")
        if not heading and not relay and last.get("pathname"):
            return True
    pathname = _resolve_probe_pathname(last)
    if pathname == "/" or (pathname and "blank" in pathname.lower()):
        return True
    return False


def _looks_like_cdp_transport_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "browser orchestrator error" in lowered
        or "browser orchestrator response timeout" in lowered
        or "operation queue timeout" in lowered
        or "operation timeout:" in lowered
        or "cdp request timeout" in lowered
        or "cdp not connected" in lowered
        or "cdp connection closed" in lowered
        or "cdp websocket closed" in lowered
        or "no target with given id" in lowered
        or "connection reset" in lowered
        or "broken pipe" in lowered
        or "connection closed before response" in lowered
    )
