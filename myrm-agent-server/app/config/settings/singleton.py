"""[INPUT]
- .app::AppSettings (POS: the composed settings model)

[OUTPUT]
- get_settings, settings

[POS]
Application settings: the process-wide settings singleton.
"""

from __future__ import annotations

from functools import lru_cache

from .app import AppSettings


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """获取全局配置实例（单例）"""
    return AppSettings()


settings = get_settings()
