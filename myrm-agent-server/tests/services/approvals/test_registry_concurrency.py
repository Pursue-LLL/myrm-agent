"""Racing resolvers decide a held reply once: it is sent or released a single time and nobody fails.

Runs on an engine set up like the production one (WAL, a deferred BEGIN that escalates to IMMEDIATE on the first write),
where two overlapping read-then-write transactions would otherwise fail the later one with "database is locked".
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.factory import register_sqlite_transaction_events, set_sqlite_pragma
from app.database.models.approval import ApprovalRecord
from app.database.models.base import Base
from app.services.approvals.registry import ApprovalRegistry

# Whether the loser of a race fails depends on how the two interleave, so one round proves little.
ROUNDS = 8


@dataclass
class RaceDb:
    sessions: async_sessionmaker[AsyncSession]
    finalized: Counter[str] = field(default_factory=Counter)

    async def seed_draft(self, approval_id: str, *, expired: bool = False) -> None:
        async with self.sessions() as db:
            db.add(
                ApprovalRecord(
                    id=approval_id,
                    agent_id="agent-1",
                    action_type="outbound_draft",
                    reason="held for review",
                    severity="warning",
                    payload={"draft_content": "hello", "draft_timeout_action": "auto_send"},
                    status="PENDING",
                    expires_at=datetime.now(timezone.utc) - timedelta(minutes=1) if expired else None,
                )
            )
            await db.commit()


@pytest.fixture()
async def race_db(tmp_path: Path) -> AsyncIterator[RaceDb]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'approvals.db'}",
        connect_args={"check_same_thread": False},
        pool_size=5,
        max_overflow=2,
    )
    event.listen(engine.sync_engine, "connect", set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db = RaceDb(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))

    @asynccontextmanager
    async def get_session() -> AsyncIterator[AsyncSession]:
        async with db.sessions() as session:
            yield session

    async def finalize(record: ApprovalRecord) -> None:
        db.finalized[record.id] += 1

    with (
        patch("app.services.approvals.registry.get_session", get_session),
        patch("app.services.approvals.registry.finalize_outbound_draft", finalize),
    ):
        yield db
    await engine.dispose()


async def test_racing_decisions_on_a_held_reply_apply_exactly_one(race_db: RaceDb) -> None:
    for round_no in range(ROUNDS):
        approval_id = f"draft-{round_no}"
        await race_db.seed_draft(approval_id)

        approved, rejected = await asyncio.gather(
            ApprovalRegistry.resolve_approval(approval_id, "approve"),
            ApprovalRegistry.resolve_approval(approval_id, "deny"),
        )

        assert (approved is None) != (rejected is None), "exactly one resolver decides the reply"

    assert race_db.finalized == Counter({f"draft-{n}": 1 for n in range(ROUNDS)})


async def test_expiry_sweep_racing_a_click_decides_the_reply_once(race_db: RaceDb) -> None:
    for round_no in range(ROUNDS):
        approval_id = f"expired-{round_no}"
        await race_db.seed_draft(approval_id, expired=True)

        swept, clicked = await asyncio.gather(
            ApprovalRegistry.cleanup_expired_approvals(),
            ApprovalRegistry.resolve_approval(approval_id, "approve"),
        )

        assert swept + (clicked is not None) == 1, "the sweep or the click decides the reply, never both"

    assert race_db.finalized == Counter({f"expired-{n}": 1 for n in range(ROUNDS)})
