"""[INPUT]
- .constants (POS: BASE_DIR)

[OUTPUT]
- LLMProvider, ProviderCacheConfig, PROVIDER_CACHE_CONFIGS, CacheSettings

[POS]
Application settings: LLM provider/cache settings.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GOOGLE = "google"
    ZHIPU = "zhipu"
    YUNSHU = "yunshu"
    XIAOMI = "xiaomi"
    OTHER = "other"


class ProviderCacheConfig:
    """Per-provider prompt cache configuration.

    Attributes:
        cache_type: auto (prefix-based), explicit (cache_control), hybrid.
        discount_rate: Cache hit discount (0.1 = 90% off).
        min_cache_tokens: Minimum tokens for caching.
        ttl_minutes: Cache TTL.
        write_cost_multiplier: Extra write cost (1.0 = none).
    """

    __slots__ = (
        "cache_type",
        "discount_rate",
        "min_cache_tokens",
        "ttl_minutes",
        "write_cost_multiplier",
    )

    def __init__(
        self,
        cache_type: Literal["auto", "explicit", "hybrid"],
        discount_rate: float,
        min_cache_tokens: int,
        ttl_minutes: int,
        write_cost_multiplier: float = 1.0,
    ) -> None:
        self.cache_type = cache_type
        self.discount_rate = discount_rate
        self.min_cache_tokens = min_cache_tokens
        self.ttl_minutes = ttl_minutes
        self.write_cost_multiplier = write_cost_multiplier


PROVIDER_CACHE_CONFIGS: dict[LLMProvider, ProviderCacheConfig] = {
    LLMProvider.ANTHROPIC: ProviderCacheConfig("hybrid", 0.1, 1024, 5, 1.25),
    LLMProvider.OPENAI: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.GOOGLE: ProviderCacheConfig("hybrid", 0.25, 1024, 60),
    LLMProvider.DEEPSEEK: ProviderCacheConfig("auto", 0.1, 64, 30),
    LLMProvider.ZHIPU: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.YUNSHU: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.XIAOMI: ProviderCacheConfig("auto", 0.5, 1024, 10),
    LLMProvider.OTHER: ProviderCacheConfig("auto", 0.5, 1024, 10),
}


class CacheSettings(BaseSettings):
    """Harness-level cache optimization toggles."""

    model_config = SettingsConfigDict(env_prefix="ENABLE_")

    prompt_caching: bool = True  # ENABLE_PROMPT_CACHING
    batch_cleanup: bool = True  # ENABLE_BATCH_CLEANUP
