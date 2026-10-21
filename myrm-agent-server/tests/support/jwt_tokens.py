"""Unsigned JWT builder for tests that need an access token with a readable ``exp`` claim."""

from __future__ import annotations

import base64
import json


def encode_segment(payload: object) -> str:
    """URL-safe, unpadded base64 of a JSON value (one JWT segment)."""
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def make_jwt(payload: object) -> str:
    """Return ``header.payload.signature`` whose payload decodes to ``payload``."""
    return f"{encode_segment({'alg': 'none'})}.{encode_segment(payload)}.signature"
