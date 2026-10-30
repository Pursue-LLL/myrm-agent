"""What the provider itself answered, read from an LLM exception.

[INPUT]
- An LLM exception and its ``__cause__``/``__context__`` chain as raised by the OpenAI and Anthropic SDKs and
  litellm: a parsed JSON ``body`` and/or an HTTP ``response``

[OUTPUT]
- MAX_CHAIN_DEPTH: how many links of an exception chain are ever read
- walk_exception_chain: the exception and its causes, outermost first, each once
- extract_error_body: the JSON-object payload of one exception, ``{}`` when it has none
- provider_error_message: the provider's own sentence for a rejected request, ``None`` when no payload came back

[POS]
The one reader of the provider's answer in an LLM exception, shared by the failure classifier, the retry-window
extractor and the error diagnostics. A failure the client library raises before anything is sent (an unknown provider
prefix, an unsupported parameter) carries no payload, so ``provider_error_message`` returns ``None`` for it instead of
the library's text.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

MAX_CHAIN_DEPTH = 6

# An aggregator nests the upstream provider's error inside its own: payload -> error.metadata.raw -> payload.
_MAX_UPSTREAM_NESTING = 2


def walk_exception_chain(exc: BaseException) -> list[BaseException]:
    """Return *exc* followed by its ``__cause__``/``__context__`` ancestors, each once, bounded by ``MAX_CHAIN_DEPTH``."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(chain) < MAX_CHAIN_DEPTH:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def extract_error_body(err: BaseException) -> dict[str, object]:
    """Return the JSON-object payload of one exception: the SDK's parsed ``body``, else the response's JSON."""
    body = getattr(err, "body", None)
    if not isinstance(body, Mapping):
        response = getattr(err, "response", None)
        try:
            body = response.json() if response is not None else None
        except Exception:
            body = None
    if isinstance(body, dict):
        return body
    return dict(body) if isinstance(body, Mapping) else {}


def provider_error_message(exc: BaseException) -> str | None:
    """Return the provider's own sentence found along the chain of *exc*, or ``None`` when the provider said nothing."""
    for err in walk_exception_chain(exc):
        message = _body_message(extract_error_body(err)) or _plain_text_payload(err)
        if message:
            return message
    return None


def _body_message(body: Mapping[str, object], depth: int = 0) -> str | None:
    error = body.get("error")
    if isinstance(error, Mapping):
        message = _upstream_message(error, depth) or _text(error.get("message"))
        if message:
            return message
    return _text(error) or _text(body.get("message")) or _text(body.get("detail"))


def _upstream_message(error: Mapping[str, object], depth: int) -> str | None:
    """Return the sentence of the upstream error an aggregator carries in ``metadata.raw``, which is more specific."""
    metadata = error.get("metadata")
    raw = metadata.get("raw") if isinstance(metadata, Mapping) else None
    if depth >= _MAX_UPSTREAM_NESTING:
        return None
    if isinstance(raw, Mapping):
        return _body_message(raw, depth + 1)
    text = _text(raw)
    if text is None or text[0] not in "{[":
        return text
    try:
        parsed = json.loads(text)
    except ValueError:
        # Truncated JSON is not a sentence, so the wrapper's own message stands.
        return None
    return _body_message(parsed, depth + 1) if isinstance(parsed, Mapping) else None


def _plain_text_payload(err: BaseException) -> str | None:
    """Return a non-JSON payload (a gateway's error page or plain text): the SDK keeps it as ``body``, httpx on the response."""
    body = getattr(err, "body", None)
    if not isinstance(body, str):
        response = getattr(err, "response", None)
        try:
            body = response.text if response is not None else None
        except Exception:
            body = None
    text = _text(body)
    # JSON that carried no message was already read above; it is data, not words for a user.
    return None if text is None or text[0] in "{[" else text


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None
