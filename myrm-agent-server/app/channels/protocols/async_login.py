"""Async login protocol for external channel authentication.

Provides framework-agnostic async login abstraction supporting multiple
authentication flows (QR code, OAuth2, API token, etc.).

[INPUT]

[OUTPUT]
- AsyncLoginProtocol: Framework-agnostic async login interface
- LoginMethod: Enum for supported login methods
- LoginStatus: Enum for login state machine
- LoginState: Frozen dataclass for type-safe login state
- LoginEvent: Event for state change notifications

[POS]
Protocol layer for external channel async login. Enables channels to
implement consistent, type-safe login flows for QR code, OAuth2, etc.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

__all__ = [
    "AsyncLoginProtocol",
    "LoginEvent",
    "LoginMethod",
    "LoginState",
    "LoginStatus",
]


class LoginMethod(Enum):
    """Supported login methods for external channels.

    Each method represents a different authentication flow pattern.
    """

    QR_CODE = "qr_code"
    OAUTH2 = "oauth2"
    API_TOKEN = "api_token"
    PASSWORD = "password"
    SSO = "sso"


class LoginStatus(Enum):
    """Login state machine status.

    Represents the current stage of the async login flow.
    """

    IDLE = "idle"
    GENERATING = "generating"
    WAITING_USER_ACTION = "waiting"
    VALIDATING = "validating"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class LoginState:
    """Type-safe login state for event streaming.

    Different login methods populate different fields:
    - QR code: qr_code_base64, qr_expires_at
    - OAuth2: oauth_authorization_url, oauth_state_token
    - API token / Password: N/A (credentials passed directly)
    """

    status: LoginStatus
    method: LoginMethod
    qr_code_base64: str | None = None
    qr_expires_at: float | None = None
    oauth_authorization_url: str | None = None
    oauth_state_token: str | None = None
    error_message: str | None = None
    progress_percent: int = 0


@dataclass(frozen=True, slots=True)
class LoginEvent:
    """Login state change event for streaming.

    Emitted by AsyncLoginProtocol.start_login() async generator.
    """

    timestamp: float
    state: LoginState
    channel_name: str
    credentials: dict[str, str] | None = None


@runtime_checkable
class AsyncLoginProtocol(Protocol):
    """Protocol for async channel login flows.

    Channels that require user interaction for authentication (QR scan,
    OAuth2 authorization) should implement this protocol. Channels using
    static credentials (API tokens, webhooks) do not need this protocol.

    Example:
        # QR code login (WeChat, WeCom, QQ)
        async for event in channel.start_login(LoginMethod.QR_CODE):
            if event.state.status == LoginStatus.WAITING_USER_ACTION:
                display_qr_code(event.state.qr_code_base64)
            elif event.state.status == LoginStatus.SUCCESS:
                save_credentials(event.credentials)
                break

        # OAuth2 login (Google Chat, MS Teams)
        async for event in channel.start_login(
            LoginMethod.OAUTH2,
            callback_url="http://localhost:3000/api/auth/callback",
        ):
            if event.state.status == LoginStatus.WAITING_USER_ACTION:
                open_browser(event.state.oauth_authorization_url)
            elif event.state.status == LoginStatus.SUCCESS:
                save_credentials(event.credentials)
                break
    """

    @property
    def supported_login_methods(self) -> list[LoginMethod]:
        """List of login methods this channel supports.

        Channels override this property in their class definition.
        """
        ...

    async def start_login(
        self,
        method: LoginMethod,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncIterator[LoginEvent]:
        """Start async login flow and stream state events.

        Args:
            method: Login method to use (must be in supported_login_methods)
            timeout: Maximum seconds to wait for user action
            callback_url: OAuth2 callback URL (required for OAuth2 method)

        Yields:
            LoginEvent: State change events (qr_generated, waiting, success, etc.)

        Raises:
            ValueError: If method is not supported by this channel
            TimeoutError: If login times out
            ChannelAuthError: If login fails
        """
        ...

    async def cancel_login(self) -> None:
        """Cancel current login flow.

        Should stop background tasks and clean up resources.
        Idempotent (safe to call multiple times).
        """
        ...
