"""Discord channel provider.

This module provides a Discord channel implementation for the Myrm Agent Harness.
It uses a dual-engine architecture to support both standalone sandbox deployments
and multi-tenant SaaS environments.
"""

from .channel import DiscordChannel
from .config import DiscordChannelConfig

__all__ = [
    "DiscordChannel",
    "DiscordChannelConfig",
]
