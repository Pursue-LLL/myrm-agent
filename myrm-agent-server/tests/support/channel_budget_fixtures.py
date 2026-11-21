"""Group ids of the channel providers and the database binding shared by the budget tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, contextmanager
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

# (channel, group id) as the providers deliver them. The ids with capitals, punctuation or a domain are the ones whose
# raw spelling differs from the session key their chats are stored under.
GROUP_IDS: tuple[tuple[str, str], ...] = (
    ("telegram", "-1001234567890"),
    ("slack", "C024BE91L"),
    ("discord", "1234567890123456789"),
    ("feishu", "oc_AbC123xyz"),
    ("matrix", "!AbCdEf:matrix.org"),
    ("whatsapp", "120363023456789012@g.us"),
    ("email", "Support@Example.com"),
    ("dingtalk", "cidAbC+def/gh=="),
)


@contextmanager
def budget_database(db: AsyncSession) -> Iterator[None]:
    """Make ``db`` the database of the channel budget service, group lookup, global recovery, budget API and audit query."""

    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession, None]:
        yield db

    def factory() -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        return session

    with (
        patch("app.services.budget.channel_budget.get_session_factory", factory),
        patch("app.services.budget.channel_budget_groups.get_session_factory", factory),
        patch("app.services.budget.enforcer.get_session_factory", factory),
        patch("app.platform_utils.get_session_factory", factory),
    ):
        yield
