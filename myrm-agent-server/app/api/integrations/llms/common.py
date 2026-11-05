"""[INPUT]
- fastapi::APIRouter (POS: route table carrier)

[OUTPUT]
- router / logger: the single APIRouter every endpoint module decorates
- _LOCAL_NO_AUTH_KEY_MARKER / _apply_local_no_auth_marker_transport_overrides: the local
  no-auth marker and its transport override, shared by discovery, verification and reachability

[POS]
Shared primitives of the LLM probe endpoints. Kept deliberately small: it only holds what more than
one endpoint module needs, so it cannot turn into a dumping ground.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

router = APIRouter()


logger = logging.getLogger(__name__)


_LOCAL_NO_AUTH_KEY_MARKER = "__myrm_local_no_auth__"


def _apply_local_no_auth_marker_transport_overrides(
    model_kwargs_raw: object,
    api_key: object,
) -> dict[str, object]:
    """Normalize model_kwargs and suppress synthetic local marker auth headers."""
    model_kwargs: dict[str, object] = dict(model_kwargs_raw) if isinstance(model_kwargs_raw, dict) else {}
    if api_key != _LOCAL_NO_AUTH_KEY_MARKER:
        return model_kwargs

    raw_extra_headers = model_kwargs.get("extra_headers")
    extra_headers = dict(raw_extra_headers) if isinstance(raw_extra_headers, dict) else {}
    extra_headers["Authorization"] = ""
    model_kwargs["extra_headers"] = extra_headers
    return model_kwargs
