"""Small helpers shared by the import-flow handler tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse


def session_context(session: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    """Patch a handler's ``get_session`` dependency with one fixed session."""

    @asynccontextmanager
    async def _context() -> AsyncIterator[AsyncSession]:
        yield session

    return _context


async def read_stream(response: StreamingResponse) -> bytes:
    """Drain a streaming response into the bytes a ZIP reader can consume."""

    return b"".join([chunk async for chunk in response.body_iterator])  # type: ignore[misc]
