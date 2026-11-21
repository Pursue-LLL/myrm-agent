"""Channel budget writes keep their change when another writer commits first, and the enforced budget is the stored one.

Every write rewrites the one stored row that holds all channel policies, from a read of that row. Under the deferred-read
transaction policy another writer committing between the read and the write aborts the write with SQLITE_BUSY_SNAPSHOT,
which ``busy_timeout`` does not cover. The budget being enforced is rebuilt from what a save stored, so two saves of one
channel that finish out of order must still leave the enforced policy equal to the stored one. The tests run the real
transaction policy on a file database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.services.budget import channel_budget
from app.services.budget.channel_budget import (
    ChannelBudgetRegistry,
    delete_channel_budget_policy,
    get_channel_budget_registry,
    load_channel_budget_policies,
    patch_channel_budget_policy,
    save_channel_budget_policy,
)
from app.services.budget.channel_budget_policy import ChannelBudgetPolicy, ChannelBudgetPolicyPatch
from tests.support.policy_sqlite import PolicyDb, policy_database, run_while_another_writer_commits

KEY = "telegram:group:g-1"
OTHER_KEY = "slack:group:c1"


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "budget.db", monkeypatch) as db:
        monkeypatch.setattr(channel_budget, "get_session_factory", lambda: db.factory)
        yield db


@pytest.fixture(autouse=True)
def _registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())


@pytest.fixture(autouse=True)
def _no_spend_query(monkeypatch: pytest.MonkeyPatch) -> None:
    # The spend query reads in a session of its own. Left in, it would be the unit's first transaction and the contention
    # these tests set up would no longer be the one the policy write has to survive.
    monkeypatch.setattr(channel_budget, "_query_channel_today_cost", AsyncMock(return_value=0.0))


def _policy(key: str, limit: float) -> ChannelBudgetPolicy:
    return ChannelBudgetPolicy(channel_key=key, daily_limit_usd=limit)


async def _stored() -> dict[str, ChannelBudgetPolicy]:
    return {policy.channel_key: policy for policy in (await load_channel_budget_policies()).policies}


@pytest.mark.asyncio
async def test_a_save_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await run_while_another_writer_commits(policy_db, lambda: save_channel_budget_policy(_policy(KEY, 7.0)))

    assert (await _stored())[KEY].daily_limit_usd == 7.0


@pytest.mark.asyncio
async def test_a_patch_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await save_channel_budget_policy(_policy(KEY, 5.0))

    await run_while_another_writer_commits(
        policy_db, lambda: patch_channel_budget_policy(KEY, ChannelBudgetPolicyPatch(enabled=False))
    )

    assert (await _stored())[KEY] == ChannelBudgetPolicy(channel_key=KEY, daily_limit_usd=5.0, enabled=False)


@pytest.mark.asyncio
async def test_a_delete_keeps_its_write_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await save_channel_budget_policy(_policy(KEY, 5.0))
    await save_channel_budget_policy(_policy(OTHER_KEY, 3.0))

    await run_while_another_writer_commits(policy_db, lambda: delete_channel_budget_policy(KEY))

    assert list(await _stored()) == [OTHER_KEY]


@pytest.mark.asyncio
async def test_the_enforced_budget_is_the_stored_one_when_saves_finish_out_of_order(
    policy_db: PolicyDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_query_reached = asyncio.Event()
    release_first_query = asyncio.Event()
    queries = 0

    async def spend_query(_channel_key: str) -> float:
        nonlocal queries
        queries += 1
        if queries == 1:
            first_query_reached.set()
            await release_first_query.wait()
        return 0.0

    monkeypatch.setattr(channel_budget, "_query_channel_today_cost", spend_query)

    slow_save = asyncio.create_task(save_channel_budget_policy(_policy(KEY, 5.0)))
    await asyncio.wait_for(first_query_reached.wait(), timeout=5)
    await save_channel_budget_policy(_policy(KEY, 9.0))  # a whole save while the first one waits on its spend query
    release_first_query.set()
    await slow_save

    assert (await _stored())[KEY] == get_channel_budget_registry().policies[KEY]
