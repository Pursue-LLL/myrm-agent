"""[INPUT]
- pydantic_settings (POS: env-backed settings base)

[OUTPUT]
- CacheSettings

[POS]
Application settings: harness-level cache optimization toggles.
"""

from __future__ import annotations

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class CacheSettings(BaseSettings):
    """Harness-level cache optimization toggles."""

    model_config = SettingsConfigDict(env_prefix="ENABLE_")

    prompt_caching: bool = True  # ENABLE_PROMPT_CACHING
    batch_cleanup: bool = True  # ENABLE_BATCH_CLEANUP
