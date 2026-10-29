"""Optional provider hooks of BaseChannel: HTTP routes, async login, OAuth2 callback, history, context document.

[INPUT]
- channels.protocols.async_login::LoginEvent (POS: state change event of an async login flow)
- channels.types::InboundMessage, ContextDocument (POS: channel message and document types)

[OUTPUT]
- ProviderHooksMixin: hooks with a safe default (no routes, login unsupported, no history, no document) that
  providers override when their platform has the capability

[POS]
Extension points the framework calls on every channel. A provider overrides only the hooks its platform supports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.channels.protocols.async_login import LoginEvent
    from app.channels.types import ContextDocument, InboundMessage


class ProviderHooksMixin:
    """Optional capabilities with default behaviour for BaseChannel."""

    # Provided by BaseChannel; declared for type checkers only.
    name: str

    def register_routes(self, registrar: object) -> None:
        """Register channel-specific HTTP routes.

        Optional method. Channels that need custom HTTP endpoints
        (e.g., webhooks, login pages, status endpoints) can override
        this to register their routes.

        The registrar parameter is typed as object to avoid coupling the
        framework layer to any specific web framework. Business layer will
        provide a RouteRegistrar implementation.

        Example:
            from app.channels.protocols import (
                HttpMethod,
                RouteMetadata,
                RouteRegistrar,
            )

            def register_routes(self, registrar: object) -> None:
                if not isinstance(registrar, RouteRegistrar):
                    return

                registrar.add_route(
                    HttpMethod.POST,
                    "webhook",
                    self._handle_webhook,
                    RouteMetadata(
                        description="Receive webhook updates",
                        requires_auth=False,
                        rate_limit_policy="60 per minute",
                    ),
                )

        Args:
            registrar: Route registration interface (from business layer)
        """
        pass

    def _get_route_prefix(self) -> str:
        """Get the route prefix for this channel.

        Default: channels/{channel_name}/
        Can be overridden by subclasses for custom prefixes.

        Returns:
            Route prefix (without leading slash)
        """
        return f"channels/{self.name}/"

    async def start_login(
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ) -> AsyncIterator[LoginEvent]:
        """Start async login flow.

        Optional method. Channels that require user interaction for
        authentication (QR scan, OAuth2) should implement AsyncLoginProtocol
        and override this method.

        The method parameter is typed as object to avoid coupling the
        framework layer base class to specific protocol types. Implementations
        should import and use LoginMethod from protocols.async_login.

        Example:
            from app.channels.protocols import (
                AsyncLoginProtocol,
                LoginMethod,
                LoginEvent,
            )
            from app.channels.helpers import QRCodeLoginHelper

            class WeChatChannel(BaseChannel):
                supported_login_methods = [LoginMethod.QR_CODE]

                async def start_login(
                    self,
                    method: object,
                    *,
                    timeout: float = 300.0,
                    callback_url: str | None = None,
                ) -> AsyncIterator[LoginEvent]:
                    if method != LoginMethod.QR_CODE:
                        raise ValueError("Only QR_CODE method is supported")

                    helper = QRCodeLoginHelper(
                        fetch_qr_fn=self._fetch_qr_code,
                        poll_status_fn=self._poll_qr_status,
                    )
                    async for event in helper.run(timeout, self.name):
                        yield event

        Args:
            method: Login method to use (LoginMethod enum)
            timeout: Maximum seconds to wait for user action
            callback_url: OAuth2 callback URL (required for OAuth2 method)

        Yields:
            LoginEvent: State change events (see AsyncLoginProtocol)

        Raises:
            NotImplementedError: On first iteration, if the channel does not support async login
        """
        raise NotImplementedError(
            f"{self.name} does not support async login (override start_login() and set supported_login_methods)"
        )
        yield  # unreachable; makes this an async generator, the shape every override has

    async def cancel_login(self) -> None:
        """Cancel current login flow.

        Optional method. Channels implementing AsyncLoginProtocol should
        override this to stop background tasks and clean up resources.

        Default implementation does nothing (safe no-op).
        """
        pass

    async def handle_oauth2_callback(
        self,
        code: str | None,
        state: str,
        error: str | None = None,
    ) -> None:
        """Handle OAuth2 authorization callback.

        Called by the server-layer callback endpoint to deliver the
        authorization code to the running OAuth2 login flow.

        Channels using OAuth2LoginHelper should override this to delegate
        to helper.handle_callback(code, state, error).

        Args:
            code: Authorization code (if user authorized)
            state: CSRF state token (validated by OAuth2LoginHelper)
            error: OAuth2 error code (if user denied)

        Raises:
            NotImplementedError: If channel does not support OAuth2 login
        """
        raise NotImplementedError(f"{self.name} does not support OAuth2 callback")

    async def fetch_history(self, chat_id: str, limit: int = 15) -> list[InboundMessage]:
        """Fetch recent historical messages from the platform's chat/thread.

        Subclasses (like Discord, Slack, etc.) should override this method to
        retrieve actual history via platform-specific APIs. Filters out Bot
        and self messages dynamically.

        Args:
            chat_id: The ID of the channel/thread to fetch from.
            limit: The maximum number of historical messages to fetch.

        Returns:
            A list of InboundMessage objects sorted in ascending chronological order.
        """
        return []

    async def read_context_document(self, msg: InboundMessage) -> ContextDocument | None:
        """The document ``msg`` is about, for turns that comment on a document; None for every other message.

        Providers whose platform can read such a document (Feishu document comments) override this. The router calls
        it just before the agent runs, so the body is never journaled or ledgered together with the inbound message.
        An override reports a read it could not complete through ``ContextDocument.status`` instead of raising.
        """
        return None
