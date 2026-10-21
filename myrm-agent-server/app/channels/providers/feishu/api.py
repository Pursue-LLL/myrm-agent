"""Feishu OpenAPI client — re-export from local SDK.

[INPUT]
- .sdk::FeishuClient (POS: Standalone Feishu OpenAPI client.)
- .sdk::FeishuAPIError, FeishuAuthError, FeishuRateLimitError, FeishuSendError
  (POS: Feishu-specific API error hierarchy.)

[OUTPUT]
- FeishuClient: async API client for Feishu OpenAPI (re-export)
- FeishuAPIError, FeishuAuthError, FeishuRateLimitError, FeishuSendError: exception hierarchy

[POS]
Re-export of Feishu SDK public surface. Canonical source: .sdk.client.
"""

from app.channels.providers.feishu.sdk import (
    FeishuAPIError,
    FeishuAuthError,
    FeishuClient,
    FeishuRateLimitError,
    FeishuSendError,
)

__all__ = [
    "FeishuClient",
    "FeishuAPIError",
    "FeishuAuthError",
    "FeishuRateLimitError",
    "FeishuSendError",
]
