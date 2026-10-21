"""WeChat channel providers.

Includes WeChatILinkChannel (iLink bridge) and WeChatOfficialChannel (Official Account).
"""

from app.channels.providers.wechat.ilink_channel import WeChatILinkChannel
from app.channels.providers.wechat.official_channel import WeChatOfficialChannel

__all__ = ["WeChatILinkChannel", "WeChatOfficialChannel"]
