"""Matrix channel — mautrix SDK with optional E2EE.

Delegates to auth.py (login/sync), handlers.py (events), crypto.py (E2EE),
html.py (markdown), media.py (uploads). Core class: lifecycle, outbound, diagnostics.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import (
    credential_field,
    credential_spec,
    parse_bool,
)
from app.channels.core.exceptions import ChannelAuthError
from app.channels.providers.matrix.auth import (
    authenticate,
    create_aiohttp_session,
    get_store_dir,
    initial_sync,
    refresh_dm_cache,
)
from app.channels.providers.matrix.handlers import (
    auto_join,
    handle_invite,
    handle_reaction,
    handle_room_message,
    register_event_handlers,
    run_sync_loop,
)
from app.channels.providers.matrix.html import (
    build_text_payload,
    convert_matrix_mentions,
)
from app.channels.providers.matrix.media import (
    send_media,
)
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 65536
_SEND_TIMEOUT = 30.0
_MEMBERS_CACHE_TTL = 300.0  # 5 minutes
_MAUTRIX_AVAILABLE = False

try:
    from mautrix.client import Client as MautrixClient
    from mautrix.types import EventType, RoomID

    _MAUTRIX_AVAILABLE = True
except ImportError:
    MautrixClient = None  # type: ignore[assignment,misc]


class MatrixChannel(BaseChannel):
    """Matrix protocol channel using mautrix SDK with optional E2EE."""

    name = "matrix"
    credential_spec = credential_spec(
        "matrixCredentials",
        homeserver=credential_field("homeserverUrl", "MATRIX_HOMESERVER"),
        access_token=credential_field(
            "accessToken", "MATRIX_ACCESS_TOKEN", required=False
        ),
        user_id=credential_field("userId", "MATRIX_USER_ID", required=False),
        password=credential_field(
            "password", "MATRIX_PASSWORD", required=False, is_sensitive=True
        ),
        device_id=credential_field("deviceId", "MATRIX_DEVICE_ID", required=False),
        encryption=credential_field(
            "encryption", "MATRIX_ENCRYPTION", default="false", required=False
        ),
        proxy=credential_field(
            "proxy", "MATRIX_PROXY", default="", required=False, is_sensitive=False
        ),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
    )

    def __init__(
        self,
        homeserver: str,
        access_token: str = "",
        *,
        user_id: str = "",
        password: str = "",
        device_id: str = "",
        encryption: str = "false",
        proxy: str = "",
    ) -> None:
        super().__init__()
        self._homeserver = homeserver.rstrip("/")
        self._access_token = access_token
        self._user_id = user_id
        self._password = password
        self._device_id = device_id
        self._encryption = parse_bool(encryption)
        self._proxy = proxy

        self._client: MautrixClient | None = None  # type: ignore[assignment]
        self._sync_task: asyncio.Task[None] | None = None
        self._dm_rooms: dict[str, bool] = {}
        self._joined_rooms: set[str] = set()
        self._room_members_cache: dict[str, dict[str, str]] = {}
        self._room_members_ts: dict[str, float] = {}

    # ── Lifecycle ──

    async def start(self) -> None:
        if not self._homeserver:
            logger.info("Matrix credentials not configured; channel idle")
            return

        if not self._access_token and not self._password:
            logger.info("Matrix: no access_token or password; channel idle")
            return

        if not _MAUTRIX_AVAILABLE:
            logger.error(
                "Matrix: mautrix not installed. "
                "Run: uv sync --extra matrix (add --extra matrix-e2ee for E2EE)"
            )
            self._status = ChannelStatus.ERROR
            return

        try:
            await self._connect()
        except Exception as exc:
            logger.warning("MatrixChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._cleanup_client()

    async def _connect(self) -> None:
        """Initialize mautrix Client, authenticate, set up E2EE, start sync loop."""
        from mautrix.api import HTTPAPI
        from mautrix.client import Client
        from mautrix.client.state_store import MemoryStateStore, MemorySyncStore
        from mautrix.types import UserID

        session = create_aiohttp_session(self._proxy)
        api = HTTPAPI(base_url=self._homeserver, token=self._access_token or "",
                      client_session=session)
        client = Client(
            mxid=UserID(self._user_id) if self._user_id else UserID(""),
            device_id=self._device_id or None, api=api,
            state_store=MemoryStateStore(), sync_store=MemorySyncStore(),
        )

        self._user_id, self._access_token = await authenticate(
            client, api, session, access_token=self._access_token,
            user_id=self._user_id, password=self._password, device_id=self._device_id,
        )
        await initial_sync(
            client, self._joined_rooms, self._dm_rooms, self._encryption, self._auto_join,
        )
        if self._encryption:
            await self._setup_encryption(client, session)

        register_event_handlers(
            client,
            self._on_room_message,
            self._on_invite,
            self._on_reaction,
        )
        self._client = client
        self._bot_id = self._user_id
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        self._sync_task = asyncio.create_task(
            run_sync_loop(client, lambda: self._status, self._auto_join)
        )
        logger.info("MatrixChannel: started (user=%s, e2ee=%s)", self._user_id, self._encryption)

    async def _setup_encryption(self, client: object, session: object) -> None:
        """Set up E2EE on the client, raising ChannelAuthError on failure."""
        from app.channels.providers.matrix.crypto import (
            check_e2ee_deps,
            setup_e2ee,
        )

        if not check_e2ee_deps():
            logger.error(
                "Matrix: encryption=true but E2EE dependencies are missing. "
                "Run: uv sync --extra matrix --extra matrix-e2ee (requires libolm)"
            )
            await session.close()  # type: ignore[union-attr]
            raise ChannelAuthError("E2EE dependencies missing", channel="matrix")

        success = await setup_e2ee(
            client,
            device_id=self._device_id or getattr(client, "device_id", "") or "",
            user_id=self._user_id,
            store_dir=get_store_dir(),
            joined_rooms=self._joined_rooms,
        )
        if not success:
            await session.close()  # type: ignore[union-attr]
            raise ChannelAuthError("E2EE initialization failed", channel="matrix")

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._sync_task:
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task
        await self._cleanup_client()
        logger.info("MatrixChannel: stopped")

    async def _cleanup_client(self) -> None:
        """Close crypto DB and aiohttp session."""
        if self._client:
            from app.channels.providers.matrix.crypto import (
                cleanup_e2ee,
            )

            await cleanup_e2ee(self._client)
            with contextlib.suppress(Exception):
                await self._client.api.session.close()
            self._client = None

    # ── Event handler wrappers ──

    async def _on_room_message(self, event: object) -> None:
        await handle_room_message(
            event,
            user_id=self._user_id,
            dm_rooms=self._dm_rooms,
            encryption=self._encryption,
            build_inbound_fn=self._build_inbound,
            emit_inbound_fn=self._emit_inbound,
        )

    async def _on_invite(self, event: object) -> None:
        await handle_invite(event, self._client, self._auto_join)

    async def _on_reaction(self, event: object) -> None:
        await handle_reaction(
            event,
            user_id=self._user_id,
            dm_rooms=self._dm_rooms,
            emit_inbound_fn=self._emit_inbound,
        )

    async def _auto_join(self, client: object, room_id: str) -> None:
        await auto_join(client, room_id)
        self._joined_rooms.add(room_id)
        await refresh_dm_cache(client, self._joined_rooms, self._dm_rooms)

    # ── Health & Diagnostics ──

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        if not self._client:
            return False
        try:
            await self._client.whoami()
            return True
        except Exception:
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._homeserver:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="homeserver URL not configured.",
                )
            )
            return issues

        if not self._access_token and not self._password:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="access_token or password not configured.",
                )
            )

        if not _MAUTRIX_AVAILABLE:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.DEPENDENCY,
                    severity=IssueSeverity.ERROR,
                    message="mautrix not installed. Run: uv sync --extra matrix",
                    fix="uv sync --extra matrix",
                )
            )

        if self._encryption:
            from app.channels.providers.matrix.crypto import (
                check_e2ee_deps,
            )

            if not check_e2ee_deps():
                issues.append(
                    ChannelIssue(
                        kind=IssueKind.DEPENDENCY,
                        severity=IssueSeverity.ERROR,
                        message=(
                            "E2EE enabled but mautrix[encryption] not installed. "
                            "Run: uv sync --extra matrix --extra matrix-e2ee "
                            "(requires libolm C library)"
                        ),
                        fix="uv sync --extra matrix --extra matrix-e2ee",
                    )
                )
            elif not self._device_id:
                issues.append(
                    ChannelIssue(
                        kind=IssueKind.CONFIG,
                        severity=IssueSeverity.WARNING,
                        message=(
                            "device_id not set. E2EE sessions won't persist across "
                            "restarts. Set a stable device_id for key persistence."
                        ),
                    )
                )

        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.AUTH,
                    severity=IssueSeverity.ERROR,
                    message="Matrix authentication failed. Check credentials.",
                )
            )
        return issues

    # ── Outbound ──

    async def send(self, msg: OutboundMessage) -> str | None:
        if self._status != ChannelStatus.RUNNING or not self._client:
            logger.debug("MatrixChannel: not running, skipping send")
            return None

        room_id = msg.recipient_id
        last_event_id: str | None = None

        for att in msg.media:
            eid = await send_media(self._client, room_id, att, self._encryption)
            if eid:
                last_event_id = eid

        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks:
                eid = await self._send_text(room_id, chunk, msg.reply_to_id)
                if eid:
                    last_event_id = eid

        return last_event_id

    async def _send_text(
        self, room_id: str, text: str, reply_to_id: str | None = None,
    ) -> str | None:
        if not self._client:
            return None

        members = await self._get_room_members(room_id)
        if members:
            text = convert_matrix_mentions(text, members)

        payload = build_text_payload(text)
        if reply_to_id:
            payload["m.relates_to"] = {"m.in_reply_to": {"event_id": reply_to_id}}

        try:
            event_id = await asyncio.wait_for(
                self._client.send_message_event(
                    RoomID(room_id), EventType.ROOM_MESSAGE, payload,
                ),
                timeout=_SEND_TIMEOUT,
            )
            return str(event_id) if event_id else None
        except Exception as exc:
            if not (self._encryption and getattr(self._client, "crypto", None)):
                logger.debug("Matrix send failed: %s", exc)
                return None
            # Retry after sharing E2EE keys
            try:
                await self._client.crypto.share_keys()
                event_id = await asyncio.wait_for(
                    self._client.send_message_event(
                        RoomID(room_id), EventType.ROOM_MESSAGE, payload,
                    ),
                    timeout=_SEND_TIMEOUT,
                )
                return str(event_id) if event_id else None
            except Exception as retry_exc:
                logger.error("Matrix: send failed after key share retry: %s", retry_exc)
                return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if not self._client:
            return
        new_content = build_text_payload(text)
        payload: dict[str, object] = {
            "msgtype": "m.text",
            "body": f"* {text}",
            "m.new_content": new_content,
            "m.relates_to": {"rel_type": "m.replace", "event_id": message_id},
        }
        try:
            await asyncio.wait_for(
                self._client.send_message_event(
                    RoomID(chat_id), EventType.ROOM_MESSAGE, payload,
                ),
                timeout=_SEND_TIMEOUT,
            )
        except Exception as exc:
            logger.debug("Matrix edit failed: %s", exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        if not self._client:
            return
        try:
            await self._client.redact(RoomID(chat_id), message_id, reason="deleted by bot")
        except Exception as exc:
            logger.debug("Matrix delete failed: %s", exc)

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        if not self._client:
            return
        payload = {
            "m.relates_to": {
                "rel_type": "m.annotation",
                "event_id": message_id,
                "key": emoji,
            },
        }
        try:
            await self._client.send_message_event(
                RoomID(chat_id), EventType.find("m.reaction"), payload,
            )
        except Exception as exc:
            logger.debug("Matrix react failed: %s", exc)

    async def start_typing(self, chat_id: str) -> None:
        if self._client:
            with contextlib.suppress(Exception):
                await self._client.set_typing(RoomID(chat_id), timeout=30000)

    async def stop_typing(self, chat_id: str) -> None:
        if self._client:
            with contextlib.suppress(Exception):
                await self._client.set_typing(RoomID(chat_id), timeout=0)

    # ── Helpers ──

    async def _get_room_members(self, room_id: str) -> dict[str, str]:
        """Get room members mapping: displayname -> qualified Matrix ID."""
        now = time.monotonic()
        cached_ts = self._room_members_ts.get(room_id, 0.0)
        if room_id in self._room_members_cache and (now - cached_ts) < _MEMBERS_CACHE_TTL:
            return self._room_members_cache[room_id]

        if not self._client:
            return {}

        try:
            members = await self._client.get_joined_members(RoomID(room_id))
            result: dict[str, str] = {}
            if isinstance(members, dict):
                for user_id, info in members.items():
                    displayname = getattr(info, "displayname", None) or getattr(
                        info, "display_name", None
                    )
                    if displayname:
                        result[displayname] = str(user_id)
            self._room_members_cache[room_id] = result
            self._room_members_ts[room_id] = now
            return result
        except Exception as exc:
            logger.debug("Matrix get_room_members failed: %s", exc)
            return {}
