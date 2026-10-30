"""Normalized view of an LLM exception for the failure classifier.

[INPUT]
- errors.error_payload::extract_error_body, parse_json_object (POS: The one reader of the provider's answer in an LLM exception)

[OUTPUT]
- NormalizedError: the HTTP status, the lower-cased message text and the parsed body of one exception
- normalize_provider_error: reads an exception into a NormalizedError, including the upstream error a gateway nests in ``error.metadata.raw``

[POS]
Input stage of the failure classifier, also used by the recovery helpers that need only a status or the message text.
It reads every place a provider's answer can sit (exception text, SDK body, response, cause chain, a gateway's nested
upstream error) into one lower-cased string the classifier's patterns run against.
"""

from __future__ import annotations

from dataclasses import dataclass

from .error_payload import extract_error_body, parse_json_object


@dataclass
class NormalizedError:
    status_code: int | None
    message: str
    body: dict[str, object]


def _extract_status_code(error: Exception) -> int | None:
    current = error
    for _ in range(5):
        code = getattr(current, "status_code", None)
        if isinstance(code, int):
            return code
        code = getattr(current, "status", None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if cause is None or cause is current:
            break
        current = cause
    return None


def normalize_provider_error(error: Exception) -> NormalizedError:
    """Extract deep nested errors (e.g. OpenRouter metadata.raw) and status codes."""
    status_code = _extract_status_code(error)
    body = extract_error_body(error)

    # Extract deeply nested message, structured error codes, and types
    _raw_msg = str(error).lower()
    _body_msg = ""
    _codes: list[str] = []
    _types: list[str] = []
    _metadata_msg = ""

    # Direct exception attributes from client SDKs (OpenAI, Anthropic, LiteLLM)
    direct_code = getattr(error, "code", None)
    if direct_code is not None and not callable(direct_code):
        _codes.append(str(direct_code).lower())
    direct_type = getattr(error, "type", None)
    if direct_type is not None and not callable(direct_type):
        _types.append(str(direct_type).lower())

    if isinstance(body, dict):
        if body.get("code"):
            _codes.append(str(body["code"]).lower())
        if body.get("type"):
            _types.append(str(body["type"]).lower())

        _err_obj = body.get("error", {})
        if isinstance(_err_obj, dict):
            _body_msg = str(_err_obj.get("message") or "").lower()
            if _err_obj.get("code"):
                _codes.append(str(_err_obj["code"]).lower())
            if _err_obj.get("type"):
                _types.append(str(_err_obj["type"]).lower())

            _metadata = _err_obj.get("metadata", {})
            if isinstance(_metadata, dict):
                _raw_json = _metadata.get("raw") or ""
                _inner = parse_json_object(_raw_json) if isinstance(_raw_json, str) and _raw_json.strip() else None
                if _inner is not None:
                    _inner_err = _inner.get("error", {})
                    if isinstance(_inner_err, dict):
                        _metadata_msg = str(_inner_err.get("message") or "").lower()
                        if _inner_err.get("code"):
                            _codes.append(str(_inner_err["code"]).lower())
                        if _inner_err.get("type"):
                            _types.append(str(_inner_err["type"]).lower())

    # Extract raw HTML or text snippet if response body is non-JSON (e.g. Cloudflare challenges)
    _resp_text = ""
    response = getattr(error, "response", None)
    if response is not None:
        text_attr = getattr(response, "text", None)
        if isinstance(text_attr, str):
            _resp_text = text_attr[:2000].lower()
        elif hasattr(response, "content"):
            content_attr = getattr(response, "content", None)
            if isinstance(content_attr, (bytes, bytearray)):
                _resp_text = content_attr[:2000].decode("utf-8", errors="ignore").lower()

    _codes_str = " ".join(_codes)
    _types_str = " ".join(_types)
    combined_message = f"{_raw_msg} | {_body_msg} | {_codes_str} | {_types_str} | {_metadata_msg} | {_resp_text}"
    return NormalizedError(status_code=status_code, message=combined_message, body=body)
