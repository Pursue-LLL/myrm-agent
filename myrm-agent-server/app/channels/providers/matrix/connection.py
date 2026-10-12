"""Matrix connection: mautrix client setup, authentication, E2EE and sync-event wiring.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstraction every provider implements; supplies _build_inbound / _emit_inbound / _set_connected)
- channels.providers.matrix.auth (POS: login, initial sync and aiohttp session creation)
- channels.providers.matrix.handlers (POS: inbound room, invite and reaction events)
- channels.providers.matrix.crypto (POS: optional E2EE setup and cleanup)

[OUTPUT]
- MatrixConnectionMixin: _connect / _setup_encryption / _cleanup_client and the room-message, invite and reaction event wrappers used by MatrixChannel

[POS]
Connection half of MatrixChannel. The host owns the credentials, the room caches and the lifecycle entry points; the mixin builds and tears down the mautrix client.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelAuthError
from app.channels.providers.matrix.auth import (
    authenticate,
    create_aiohttp_session,
    get_store_dir,
    initial_sync,
)
from app.channels.providers.matrix.handlers import (
    handle_invite,
    handle_reaction,
    handle_room_message,
    register_event_handlers,
    run_sync_loop,
)
from app.channels.types import (
    ChannelStatus,
)

if TYPE_CHECKING:
    import aiohttp
    from mautrix.client import Client as MautrixClient

logger = logging.getLogger(__name__)


class MatrixConnectionMixin(BaseChannel):
    """mautrix client setup and sync-event wiring for ``MatrixChannel``.

    Requires the host class to provide the attributes below plus ``_auto_join``.
    """

    _homeserver: str
    _access_token: str
    _user_id: str
    _password: str
    _device_id: str
    _encryption: bool
    _proxy: str
    _client: MautrixClient | None
    _sync_task: asyncio.Task[None] | None
    _dm_rooms: dict[str, bool]
    _joined_rooms: set[str]

    if TYPE_CHECKING:

        async def _auto_join(self, client: object, room_id: str) -> None: ...

    async def _connect(self) -> None:
        """Initialize mautrix Client, authenticate, set up E2EE, start sync loop."""
        from mautrix.api import HTTPAPI
        from mautrix.client import Client
        from mautrix.client.state_store import MemoryStateStore, MemorySyncStore
        from mautrix.types import UserID

        session = create_aiohttp_session(self._proxy)
        api = HTTPAPI(base_url=self._homeserver, token=self._access_token or "", client_session=session)
        client = Client(
            mxid=UserID(self._user_id) if self._user_id else UserID(""),
            device_id=self._device_id or None,
            api=api,
            state_store=MemoryStateStore(),
            sync_store=MemorySyncStore(),
        )

        self._user_id, self._access_token = await authenticate(
            client,
            api,
            session,
            access_token=self._access_token,
            user_id=self._user_id,
            password=self._password,
            device_id=self._device_id,
        )
        await initial_sync(
            client,
            self._joined_rooms,
            self._dm_rooms,
            self._encryption,
            self._auto_join,
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
        self._sync_task = asyncio.create_task(run_sync_loop(client, lambda: self._status, self._auto_join))
        logger.info("MatrixChannel: started (user=%s, e2ee=%s)", self._user_id, self._encryption)

    async def _setup_encryption(self, client: object, session: aiohttp.ClientSession) -> None:
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
            await session.close()
            raise ChannelAuthError("E2EE dependencies missing", channel="matrix")

        success = await setup_e2ee(
            client,
            device_id=self._device_id or getattr(client, "device_id", "") or "",
            user_id=self._user_id,
            store_dir=get_store_dir(),
            joined_rooms=self._joined_rooms,
        )
        if not success:
            await session.close()
            raise ChannelAuthError("E2EE initialization failed", channel="matrix")

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
