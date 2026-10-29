"""Browser takeover live-assist links on agent stream events.

[INPUT]
- app.remote_access.pairing::create_pairing_token (POS: HMAC-signed pairing tokens with TTL for mobile remote access deep links)
- app.remote_access.pairing_links::mobile_path_for_pairing_token, mobile_url_for_path (POS: shared pairing deep-link path and absolute mobile URL derivation)

[OUTPUT]
- inject_takeover_live_assist_url: adds the signed live-assist link to a browser takeover event (a
  ``browser_takeover_requested`` event or an ``approval_required`` event for ``browser_takeover``), reusing the
  link of the previous identical request
- TakeoverLiveAssistCache: ``(cache_key, live_assist_url)`` carried between events of one stream

[POS]
Server-side link signing for browser takeover. The agent stream calls it on every event; events that are no takeover
pass through untouched, and a managed browser (reachable without a link) gets none.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAKEOVER_REASON_MAX_CHARS = 280
_TAKEOVER_PAGE_URL_MAX_CHARS = 1024
_TAKEOVER_MESSAGE_ID_MAX_CHARS = 256
TakeoverLiveAssistCache = tuple[str, str]


def _clamp_takeover_context(value: object, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    trimmed = value.strip()
    if not trimmed:
        return ""
    return trimmed[:max_chars]


def _event_with_mutable_data(
    event: object,
) -> tuple[dict[str, object], dict[str, object]] | None:
    if isinstance(event, dict):
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}
            event["data"] = data
        return event, data

    if hasattr(event, "to_dict"):
        event_dict = event.to_dict()
    elif hasattr(event, "model_dump"):
        event_dict = event.model_dump()
    else:
        return None

    if not isinstance(event_dict, dict):
        return None
    data = event_dict.get("data")
    if not isinstance(data, dict):
        data = {}
        event_dict["data"] = data
    return event_dict, data


def _compose_takeover_live_assist_url(
    base_url_or_path: str,
    *,
    message_id: str,
    reason: str,
    page_url: str,
) -> str:
    parts = urlsplit(base_url_or_path)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if message_id:
        query["mid"] = message_id
    if reason:
        query["reason"] = reason
    if page_url:
        query["page"] = page_url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def _create_takeover_live_assist_url(
    *,
    chat_id: str | None,
    message_id: str | None,
    reason: object,
    page_url: object,
    is_managed: bool,
) -> str | None:
    normalized_chat_id = _clamp_takeover_context(chat_id, 128)
    if not normalized_chat_id or is_managed:
        return None

    from app.remote_access.pairing import BROWSER_TAKEOVER_PURPOSE, create_pairing_token
    from app.remote_access.pairing_links import (
        mobile_path_for_pairing_token,
        mobile_url_for_path,
    )

    token = create_pairing_token(
        chat_id=normalized_chat_id,
        purpose=BROWSER_TAKEOVER_PURPOSE,
    )
    mobile_path = mobile_path_for_pairing_token(
        token=token,
        purpose=BROWSER_TAKEOVER_PURPOSE,
        chat_id=normalized_chat_id,
    )
    absolute_url = await mobile_url_for_path(mobile_path)
    entry_url = absolute_url or mobile_path
    return _compose_takeover_live_assist_url(
        entry_url,
        message_id=_clamp_takeover_context(message_id, _TAKEOVER_MESSAGE_ID_MAX_CHARS),
        reason=_clamp_takeover_context(reason, _TAKEOVER_REASON_MAX_CHARS),
        page_url=_clamp_takeover_context(page_url, _TAKEOVER_PAGE_URL_MAX_CHARS),
    )


def _read_live_assist_url(payload: dict[str, object]) -> str:
    value = payload.get("live_assist_url")
    return value.strip() if isinstance(value, str) else ""


def _is_managed_takeover(payload: dict[str, object], fallback: dict[str, object]) -> bool:
    payload_flag = payload.get("is_managed")
    if isinstance(payload_flag, bool):
        return payload_flag
    fallback_flag = fallback.get("is_managed")
    return isinstance(fallback_flag, bool) and fallback_flag


def _takeover_cache_key(*, reason: object, page_url: object, is_managed: bool) -> str:
    return "|".join(
        [
            "managed" if is_managed else "extension",
            _clamp_takeover_context(reason, _TAKEOVER_REASON_MAX_CHARS),
            _clamp_takeover_context(page_url, _TAKEOVER_PAGE_URL_MAX_CHARS),
        ]
    )


async def inject_takeover_live_assist_url(
    event: object,
    *,
    chat_id: str | None,
    message_id: str | None,
    cached: TakeoverLiveAssistCache | None,
) -> tuple[object, TakeoverLiveAssistCache | None]:
    event_type = getattr(event, "type", None) if not isinstance(event, dict) else event.get("type")
    if event_type not in {"browser_takeover_requested", "approval_required"}:
        return event, cached

    event_pair = _event_with_mutable_data(event)
    if event_pair is None:
        return event, cached
    event_dict, event_data = event_pair

    if event_type == "browser_takeover_requested":
        if message_id:
            event_dict.setdefault("messageId", message_id)
            event_data.setdefault("messageId", message_id)
        existing = _read_live_assist_url(event_data)
        is_managed = _is_managed_takeover(event_data, event_data)
        if is_managed:
            return event_dict, cached
        cache_key = _takeover_cache_key(
            reason=event_data.get("reason"),
            page_url=event_data.get("url"),
            is_managed=is_managed,
        )
        if existing:
            return event_dict, (cache_key, existing)
        live_assist_url: str | None
        if cached and cached[0] == cache_key:
            live_assist_url = cached[1]
        else:
            live_assist_url = await _create_takeover_live_assist_url(
                chat_id=chat_id,
                message_id=message_id,
                reason=event_data.get("reason"),
                page_url=event_data.get("url"),
                is_managed=is_managed,
            )
        if live_assist_url:
            event_data["live_assist_url"] = live_assist_url
            return event_dict, (cache_key, live_assist_url)
        return event_dict, cached

    action_type = event_data.get("action_type")
    if action_type != "browser_takeover":
        return event_dict, cached

    takeover_payload = event_data.get("payload")
    takeover_data = takeover_payload if isinstance(takeover_payload, dict) else event_data
    is_managed = _is_managed_takeover(takeover_data, event_data)
    if is_managed:
        return event_dict, cached
    cache_key = _takeover_cache_key(
        reason=takeover_data.get("reason", event_data.get("reason")),
        page_url=takeover_data.get("url", event_data.get("url")),
        is_managed=is_managed,
    )
    existing = _read_live_assist_url(takeover_data)
    if existing:
        if "live_assist_url" not in event_data:
            event_data["live_assist_url"] = existing
        return event_dict, (cache_key, existing)

    if cached and cached[0] == cache_key:
        live_assist_url = cached[1]
    else:
        live_assist_url = await _create_takeover_live_assist_url(
            chat_id=chat_id,
            message_id=message_id,
            reason=takeover_data.get("reason", event_data.get("reason")),
            page_url=takeover_data.get("url", event_data.get("url")),
            is_managed=is_managed,
        )
    if not live_assist_url:
        return event_dict, cached

    takeover_data["live_assist_url"] = live_assist_url
    if isinstance(takeover_payload, dict):
        event_data["payload"] = takeover_data
    event_data["live_assist_url"] = live_assist_url
    return event_dict, (cache_key, live_assist_url)
