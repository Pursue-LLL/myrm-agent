"""WeCom self-built application API constants shared by the channel and its inbound mixin.

[INPUT]
- (none)

[OUTPUT]
- API_BASE: WeCom API base URL
- SEND_TIMEOUT / UPLOAD_TIMEOUT: HTTP timeouts in seconds
- TOKEN_REFRESH_BUFFER: seconds before expiry at which the access token is refreshed

[POS]
Static configuration for WeCom API calls.
"""

from __future__ import annotations

API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"
SEND_TIMEOUT = 15.0
UPLOAD_TIMEOUT = 30.0
TOKEN_REFRESH_BUFFER = 300
