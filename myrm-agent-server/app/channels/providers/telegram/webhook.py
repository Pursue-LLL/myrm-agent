"""Telegram webhook registration, verification, and FastAPI route binding.

Mixin providing webhook lifecycle and HTTP endpoint registration for TelegramChannel.

[INPUT]
- channels.security::WebhookSecurityMiddleware, WebhookResponseError
- channels.protocols.route_registrar::HttpMethod, RouteMetadata, RouteRegistrar, GenericRequest, GenericResponse
- fastapi::Request
- telegram.inbound::_ALLOWED_UPDATES

[OUTPUT]
- TelegramWebhookMixin: verify, handle_webhook_update, register_routes, webhook setup/cleanup

[POS]
Telegram webhook mixin. Validates X-Telegram-Bot-Api-Secret-Token, registers POST
/webhook with security middleware, and manages setWebhook/deleteWebhook lifecycle.
"""

from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from fastapi import Request

from app.channels.security.errors import WebhookResponseError

from .api_core import TelegramApiError
from .inbound import _ALLOWED_UPDATES

if TYPE_CHECKING:
    from app.channels.protocols.route_registrar import GenericRequest, GenericResponse
    from app.channels.types import InboundMessage

    from .api import TelegramClient
    from .helpers import BotCommand

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _JsonResponse:
    """Webhook HTTP response implementing the GenericResponse protocol."""

    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class TelegramWebhookMixin:
    """Mixin providing Telegram webhook verification and route registration.

    Requires the host class to have:
    - self._client: TelegramClient
    - self._token, self._webhook_url, self._commands
    - self.webhook_secret, self.is_webhook_mode, self._redact(text)
    - self._parse_update, self._pre_emit_hook, self._buffer_or_emit
    - self._register_commands (via this mixin)
    """

    _client: TelegramClient
    _token: str
    _webhook_url: str
    _commands: list[BotCommand]

    if TYPE_CHECKING:
        # Provided by the host channel and its other mixins; declared with their signatures for the type checker.
        @property
        def webhook_secret(self) -> str: ...
        def _redact(self, text: str) -> str: ...
        def _parse_update(self, update: dict[str, object]) -> InboundMessage | None: ...
        async def _pre_emit_hook(self, msg: InboundMessage) -> InboundMessage | None: ...
        async def _buffer_or_emit(self, msg: InboundMessage, update: dict[str, object]) -> None: ...

    async def verify(self, request: Request, body: bytes) -> None:
        """SignatureVerifier Protocol: validate X-Telegram-Bot-Api-Secret-Token header."""
        actual = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(actual, self.webhook_secret):
            raise WebhookResponseError(
                status_code=403,
                error_type="signature-invalid",
                title="Invalid Signature",
                detail="Telegram webhook secret token verification failed",
                trace_id=request.state._webhook_trace_id if hasattr(request.state, "_webhook_trace_id") else "",
            )

    async def handle_webhook_update(self, update: dict[str, object]) -> None:
        """Process a Telegram webhook update (called by FastAPI endpoint)."""
        msg = self._parse_update(update)
        if msg:
            msg = await self._pre_emit_hook(msg)
            if msg:
                await self._buffer_or_emit(msg, update)

    async def _register_commands(self) -> None:
        """Register bot commands via setMyCommands."""
        if not self._commands:
            await self._client.delete_my_commands()
            return
        try:
            await self._client.set_my_commands(
                [{"command": cmd.command, "description": cmd.description} for cmd in self._commands]
            )
            logger.warning("TelegramChannel: registered %d commands", len(self._commands))
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: setMyCommands failed: %s", exc)

    async def _setup_webhook(self) -> None:
        """Register the webhook URL with Telegram via setWebhook API."""
        await self._client.set_webhook(
            self._webhook_url,
            secret_token=self.webhook_secret,
            allowed_updates=_ALLOWED_UPDATES,
        )
        logger.warning("TelegramChannel: webhook registered at %s", self._webhook_url)

    async def _cleanup_webhook(self) -> None:
        """Remove any registered webhook. Best-effort."""
        try:
            await self._client.delete_webhook()
        except Exception as exc:
            logger.debug("TelegramChannel: deleteWebhook failed: %s", self._redact(str(exc)))

    def register_routes(self, registrar: object) -> None:
        """Register custom HTTP routes for Telegram webhook.

        Registers POST /webhook endpoint for receiving Telegram Bot API updates.
        Applies WebhookSecurityMiddleware for signature verification and rate limiting.

        Args:
            registrar: RouteRegistrar Protocol implementation (e.g., FastAPIRouteRegistrar)
        """
        from app.channels.protocols.route_registrar import (
            HttpMethod,
            RouteMetadata,
            RouteRegistrar,
        )
        from app.channels.security import (
            SecurityLimits,
            SecurityProtocols,
            WebhookSecurityMiddleware,
        )

        if not isinstance(registrar, RouteRegistrar):
            logger.warning("TelegramChannel: registrar does not implement RouteRegistrar; webhook route not registered")
            return

        middleware = WebhookSecurityMiddleware(
            limits=SecurityLimits(
                body_limit_pre_auth=10_000,
                body_limit_post_auth=10_000,
                read_timeout_seconds=5.0,
            ),
            protocols=SecurityProtocols(signature_verifier=self),
        )

        async def webhook_handler(request: GenericRequest) -> GenericResponse:
            """Handle Telegram webhook updates."""
            try:
                # The registrar hands over an adapter that forwards every FastAPI Request attribute the middleware reads.
                ctx = await middleware.process_request(cast("Request", request), "telegram")

                if ctx.parsed_data is None:
                    return _JsonResponse(400, b'{"ok": false, "error": "Invalid JSON"}')

                await self.handle_webhook_update(ctx.parsed_data)

            except WebhookResponseError as e:
                return _JsonResponse(e.status_code, json.dumps(e.to_dict()).encode("utf-8"))
            except Exception as e:
                logger.warning("Telegram webhook error: %s", e, exc_info=True)
                return _JsonResponse(500, json.dumps({"ok": False, "error": "Internal error"}).encode("utf-8"))

            return _JsonResponse(200, b'{"ok": true}')

        registrar.add_route(
            method=HttpMethod.POST,
            path="webhook",
            handler=webhook_handler,
            metadata=RouteMetadata(
                description="Receive Telegram Bot API webhook updates",
                requires_auth=False,
            ),
        )
