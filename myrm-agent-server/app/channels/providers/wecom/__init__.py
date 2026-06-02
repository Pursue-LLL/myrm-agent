"""WeCom (Enterprise WeChat) channel providers.

Includes WeComChannel (self-built app) and WeComAiBotChannel (AI Bot).
"""

from app.channels.providers.wecom.aibot_channel import WeComAiBotChannel
from app.channels.providers.wecom.channel import WeComChannel

__all__ = ["WeComAiBotChannel", "WeComChannel"]
