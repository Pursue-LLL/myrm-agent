"""Shared E2E frontend credential helpers."""

from __future__ import annotations

import sys

from tests.support.test_secrets import apply_test_secrets_to_environ, load_test_secrets


def require_basic_llm_credentials() -> tuple[str, str, str]:
    """Return (api_key, base_url, model) from [T] secrets or exit."""
    apply_test_secrets_to_environ()
    secrets = load_test_secrets()
    if not secrets.has_basic_credentials:
        print("Error: BASIC_MODEL and BASIC_API_KEY must be set in myrm-agent-server/.env.test")
        sys.exit(1)
    base_url = secrets.basic_base_url
    if not base_url:
        print("Error: BASIC_BASE_URL must be set in myrm-agent-server/.env.test")
        sys.exit(1)
    return secrets.basic_api_key, base_url, secrets.basic_model


def require_lite_llm_credentials() -> tuple[str, str, str]:
    """Return (api_key, base_url, model) from [T] secrets or exit."""
    apply_test_secrets_to_environ()
    secrets = load_test_secrets()
    if not secrets.has_lite_credentials:
        print("Error: LITE_MODEL and LITE_API_KEY must be set in myrm-agent-server/.env.test")
        sys.exit(1)
    lite_key = secrets.lite_api_key or secrets.basic_api_key
    lite_url = secrets.lite_base_url or secrets.basic_base_url
    lite_model = secrets.lite_model or secrets.basic_model
    if not lite_url:
        print("Error: LITE_BASE_URL or BASIC_BASE_URL must be set in myrm-agent-server/.env.test")
        sys.exit(1)
    return lite_key, lite_url, lite_model
