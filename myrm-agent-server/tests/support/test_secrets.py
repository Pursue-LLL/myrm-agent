"""@input: dotenv_values, pathlib (stdlib)
@output: TestSecrets, load_test_secrets(), apply_test_secrets_to_environ(), resolve_test_env()
@pos: [T] pytest-only secrets loader — structured access to `.env.test` without server runtime coupling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class TestSecrets:
    """Structured view of [T] business and harness toggles from ``.env.test``."""

    raw: Mapping[str, str | None]

    def get(self, key: str, default: str = "") -> str:
        value = self.raw.get(key)
        if value is None:
            return default
        return str(value).strip()

    @property
    def basic_api_key(self) -> str:
        return self.get("BASIC_API_KEY")

    @property
    def basic_base_url(self) -> str:
        return self.get("BASIC_BASE_URL")

    @property
    def basic_model(self) -> str:
        return self.get("BASIC_MODEL")

    @property
    def lite_api_key(self) -> str:
        return self.get("LITE_API_KEY")

    @property
    def lite_base_url(self) -> str:
        return self.get("LITE_BASE_URL")

    @property
    def lite_model(self) -> str:
        return self.get("LITE_MODEL")

    @property
    def has_basic_credentials(self) -> bool:
        return bool(self.basic_model and self.basic_api_key)

    @property
    def has_lite_credentials(self) -> bool:
        lite_key = self.lite_api_key or self.basic_api_key
        lite_model = self.lite_model or self.basic_model
        return bool(lite_model and lite_key)

    @property
    def has_search_credentials(self) -> bool:
        service = self.get("SEARCH_SERVICE")
        if service == "tavily":
            return bool(self.get("TAVILY_API_KEY"))
        if service == "searxng":
            return bool(self.get("SEARXNG_URL"))
        return False


@lru_cache(maxsize=1)
def load_test_secrets() -> TestSecrets:
    """Load [T] secrets from disk once per process."""
    for path in (_SERVER_ROOT / ".env.test", _SERVER_ROOT / ".env.test.example"):
        if path.exists():
            values = dotenv_values(path)
            normalized = {key: value for key, value in values.items() if value is not None}
            return TestSecrets(raw=normalized)
    return TestSecrets(raw={})


def clear_test_secrets_cache() -> None:
    """Clear cached secrets (for tests that mutate fixture files)."""
    load_test_secrets.cache_clear()


def apply_test_secrets_to_environ(
    secrets: TestSecrets | None = None,
    *,
    overwrite: bool = True,
) -> None:
    """Expose [T] secrets on ``os.environ`` for legacy import-time ``getenv`` checks."""
    resolved = secrets or load_test_secrets()
    for key, value in resolved.raw.items():
        if value is None:
            continue
        stripped = str(value).strip()
        if not stripped:
            continue
        if overwrite or key not in os.environ:
            os.environ[key] = stripped


def resolve_test_env(key: str, default: str = "") -> str:
    """Resolve from ``os.environ`` first (monkeypatch/apply), then [T] secrets file."""
    env_value = os.getenv(key)
    if env_value is not None and env_value.strip():
        return env_value.strip()
    return load_test_secrets().get(key, default)


def require_test_env(secrets: TestSecrets, key: str) -> str:
    """Return a required [T] secret or raise."""
    value = secrets.get(key)
    if not value:
        raise RuntimeError(f"{key} must be set in .env.test")
    return value
