"""OAuth2 login helper for external channel authentication.

Provides reusable OAuth2 authorization code flow with CSRF protection.

[INPUT]

[OUTPUT]
- OAuth2LoginHelper: Reusable OAuth2 login flow executor

[POS]
Helper layer for implementing AsyncLoginProtocol with OAuth2 method.
Encapsulates authorization URL generation, CSRF state, callback handling.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import urlencode

from app.channels.core.exceptions import (
    ChannelAuthError,
)
from app.channels.protocols.async_login import (
    LoginEvent,
    LoginMethod,
    LoginState,
    LoginStatus,
)

logger = logging.getLogger(__name__)

__all__ = ["OAuth2LoginHelper"]


class OAuth2LoginHelper:
    """OAuth2 authorization code flow helper with CSRF protection.

    Encapsulates OAuth2 login pattern:
    1. Generate authorization URL with CSRF state
    2. Wait for user to authorize in browser
    3. Handle callback with authorization code
    4. Exchange code for credentials
    5. Return credentials on success

    Example:
        helper = OAuth2LoginHelper(
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            client_id="your-client-id",
            client_secret="your-client-secret",
            scope=["https://www.googleapis.com/auth/chat.bot"],
            callback_handler=lambda code: exchange_code_for_token(code),
        )

        async for event in helper.run(
            callback_url="http://localhost:3000/api/auth/callback",
            timeout=300.0,
            channel_name="google_chat",
        ):
            if event.state.status == LoginStatus.WAITING_USER_ACTION:
                open_browser(event.state.oauth_authorization_url)
            elif event.state.status == LoginStatus.SUCCESS:
                save_credentials(event.credentials)
                break
    """

    def __init__(
        self,
        authorization_endpoint: str,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        scope: list[str],
        callback_handler: Callable[[str, str], Awaitable[dict[str, str]]],
    ) -> None:
        """Initialize OAuth2 login helper.

        Args:
            authorization_endpoint: OAuth2 authorization URL
            token_endpoint: OAuth2 token exchange endpoint
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            scope: List of OAuth2 permission scopes
            callback_handler: Function to exchange authorization code for credentials
                (receives code and state, returns credentials dict)
        """
        self._authorization_endpoint = authorization_endpoint
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._callback_handler = callback_handler
        self._cancelled = False
        self._callback_received = asyncio.Event()
        self._callback_code: str | None = None
        self._callback_error: str | None = None
        self._csrf_state: str | None = None

    async def run(
        self,
        callback_url: str,
        timeout: float,
        channel_name: str,
    ) -> AsyncIterator[LoginEvent]:
        """Execute OAuth2 login flow with state streaming.

        Args:
            callback_url: OAuth2 redirect URI (e.g., "http://localhost:3000/api/auth/callback")
            timeout: Maximum seconds to wait for authorization
            channel_name: Channel name for event metadata

        Yields:
            LoginEvent: State change events

        Raises:
            TimeoutError: If authorization times out
            ChannelAuthError: If OAuth2 flow fails
        """
        self._cancelled = False
        self._callback_received.clear()
        self._callback_code = None
        self._callback_error = None

        yield self._create_event(
            LoginState(
                status=LoginStatus.GENERATING,
                method=LoginMethod.OAUTH2,
                progress_percent=10,
            ),
            channel_name,
        )

        self._csrf_state = secrets.token_urlsafe(32)
        csrf_state = self._csrf_state

        auth_params = {
            "client_id": self._client_id,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": " ".join(self._scope),
            "state": csrf_state,
        }
        authorization_url = f"{self._authorization_endpoint}?{urlencode(auth_params)}"

        logger.info(
            "OAuth2 authorization URL generated",
            extra={"channel": channel_name, "state": csrf_state[:8]},
        )

        yield self._create_event(
            LoginState(
                status=LoginStatus.WAITING_USER_ACTION,
                method=LoginMethod.OAUTH2,
                oauth_authorization_url=authorization_url,
                oauth_state_token=csrf_state,
                progress_percent=30,
            ),
            channel_name,
        )

        try:
            await asyncio.wait_for(self._callback_received.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(
                "OAuth2 login timeout",
                extra={"channel": channel_name},
            )
            yield self._create_event(
                LoginState(
                    status=LoginStatus.TIMEOUT,
                    method=LoginMethod.OAUTH2,
                    error_message="Login timeout: user did not authorize",
                ),
                channel_name,
            )
            raise TimeoutError(f"{channel_name} OAuth2 login timeout") from None

        if self._cancelled:
            yield self._create_event(
                LoginState(
                    status=LoginStatus.CANCELLED,
                    method=LoginMethod.OAUTH2,
                ),
                channel_name,
            )
            return

        if self._callback_error:
            logger.error(
                "OAuth2 callback error",
                extra={"channel": channel_name, "error": self._callback_error},
            )
            yield self._create_event(
                LoginState(
                    status=LoginStatus.FAILED,
                    method=LoginMethod.OAUTH2,
                    error_message=self._callback_error,
                ),
                channel_name,
            )
            raise ChannelAuthError(
                f"OAuth2 callback error: {self._callback_error}",
                channel=channel_name,
            )

        if not self._callback_code:
            yield self._create_event(
                LoginState(
                    status=LoginStatus.FAILED,
                    method=LoginMethod.OAUTH2,
                    error_message="No authorization code received",
                ),
                channel_name,
            )
            raise ChannelAuthError(
                "OAuth2 callback missing code",
                channel=channel_name,
            )

        yield self._create_event(
            LoginState(
                status=LoginStatus.VALIDATING,
                method=LoginMethod.OAUTH2,
                progress_percent=70,
            ),
            channel_name,
        )

        try:
            credentials = await self._callback_handler(self._callback_code, csrf_state)
        except Exception as exc:
            logger.error(
                "OAuth2 token exchange failed",
                extra={"channel": channel_name, "error": str(exc)},
                exc_info=True,
            )
            yield self._create_event(
                LoginState(
                    status=LoginStatus.FAILED,
                    method=LoginMethod.OAUTH2,
                    error_message=f"Token exchange failed: {exc}",
                ),
                channel_name,
            )
            raise ChannelAuthError(
                f"OAuth2 token exchange failed: {exc}",
                channel=channel_name,
            ) from exc

        logger.info(
            "OAuth2 login successful",
            extra={"channel": channel_name},
        )
        yield self._create_event(
            LoginState(
                status=LoginStatus.SUCCESS,
                method=LoginMethod.OAUTH2,
                progress_percent=100,
            ),
            channel_name,
            credentials,
        )

    async def handle_callback(
        self,
        code: str | None,
        state: str,
        error: str | None = None,
    ) -> None:
        """Handle OAuth2 callback from redirect URI.

        Should be called by business layer's callback endpoint.

        Args:
            code: Authorization code (if success)
            state: CSRF state token (must match the generated CSRF state)
            error: OAuth2 error code (if authorization denied)
        """
        if error:
            self._callback_error = error
        elif not secrets.compare_digest(state, self._csrf_state or ""):
            logger.warning("OAuth2 CSRF state mismatch: callback rejected")
            self._callback_error = "CSRF state mismatch: possible cross-site request forgery"
        else:
            self._callback_code = code

        self._callback_received.set()

    def cancel(self) -> None:
        """Cancel current login flow."""
        self._cancelled = True
        self._callback_received.set()
        logger.info("OAuth2 login cancelled")

    def _create_event(
        self,
        state: LoginState,
        channel_name: str,
        credentials: dict[str, str] | None = None,
    ) -> LoginEvent:
        """Create login event with current timestamp."""
        return LoginEvent(
            timestamp=time.time(),
            state=state,
            channel_name=channel_name,
            credentials=credentials,
        )
