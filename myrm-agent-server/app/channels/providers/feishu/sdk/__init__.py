"""Feishu/Lark OpenAPI SDK — standalone HTTP client for Feishu platform APIs.

Provides ``FeishuClient`` for token management, messaging, document,
and media operations via Feishu's OpenAPI.

[INPUT]
- .client::FeishuClient (POS: Standalone Feishu OpenAPI client.)
- .exceptions::FeishuAPIError, FeishuAuthError, FeishuRateLimitError, FeishuSendError
  (POS: Feishu-specific API error hierarchy.)

[OUTPUT]
- FeishuClient: async API client for Feishu OpenAPI
- FeishuAPIError, FeishuAuthError, FeishuRateLimitError, FeishuSendError: exception hierarchy

[POS]
Package init for feishu SDK. Re-exports the public API surface.
"""

from app.channels.providers.feishu.sdk.client import FeishuClient
from app.channels.providers.feishu.sdk.exceptions import (
    FeishuAPIError,
    FeishuAuthError,
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
