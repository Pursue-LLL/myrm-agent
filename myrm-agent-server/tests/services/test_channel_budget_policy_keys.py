"""A policy meets the messages and the spend of its group however its key was typed or stored.

Real SQLite, the real budget API handlers and the real session keys of inbound messages: the key typed in the settings
page, the row stored with its key in any spelling, the chats stored under the session key and the key of the live
message all have to agree. A key that is not of the form {channel}:group:{chat id} is rejected instead of becoming a
policy that never applies. Every stored policy, enabled or not, is listed after a restart.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget.router import (
    ChannelBudgetPolicyRequest,
    delete_channel_budget,
    get_channel_audit,
    get_channel_budgets,
    update_channel_budget,
)
from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.session import build_channel_budget_key, build_channel_session_key
from app.core.utils.errors import StandardHTTPException
from app.database.models.config import UserConfig
from app.services.budget import channel_budget
from app.services.budget.channel_budget import (
    CHANNEL_BUDGET_CONFIG_KEY,
    ChannelBudgetRegistry,
    get_channel_budget_registry,
    initialize_channel_budgets,
    load_channel_budget_policies,
    record_channel_cost,
    save_channel_budget_policy,
    should_block_channel,
)
from app.services.budget.channel_budget_policy import ChannelBudgetPolicy
from tests.support.channel_budget_fixtures import GROUP_IDS, budget_database
from tests.support.channel_chat_rows import seed_channel_chat, seed_costed_reply


@pytest.fixture(autouse=True)
def _database(db_session: AsyncSession) -> Iterator[None]:
    with budget_database(db_session):
        yield


@pytest.fixture(autouse=True)
def _registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())


def _group_message(channel: str, peer: str) -> InboundMessage:
    return InboundMessage(
        channel=channel, sender_id="u1", content="hi", chat_id=peer, is_group=True, sent_at=1.0, sent_timezone="UTC"
    )


def _limit(usd: float) -> ChannelBudgetPolicyRequest:
    return ChannelBudgetPolicyRequest(daily_limit_usd=usd)


async def _spend_in_group(db: AsyncSession, msg: InboundMessage, cost_usd: float) -> None:
    """Store a costed reply in the chat the router would open for ``msg`` today."""
    key = f"{build_channel_session_key(msg)}:e=2026-10-27"
    await seed_costed_reply(db, await seed_channel_chat(db, key), cost_usd)


async def _store_raw_policies(db: AsyncSession, *entries: tuple[str, float]) -> None:
    """Store a policy row with its keys exactly as typed."""
    policies = [{"channel_key": key, "daily_limit_usd": limit} for key, limit in entries]
    db.add(
        UserConfig(
            id="cfg-channel-budgets",
            config_key=CHANNEL_BUDGET_CONFIG_KEY,
            config_value={"policies": policies},
            version="1_0",
            last_device_id="server",
            is_encrypted=False,
        )
    )
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(("channel", "peer"), GROUP_IDS)
async def test_a_policy_typed_as_the_id_was_delivered_blocks_its_group(channel: str, peer: str) -> None:
    key = build_channel_budget_key(_group_message(channel, peer))

    await update_channel_budget(f" {channel.capitalize()}:group:{peer} ", _limit(1.0))
    record_channel_cost(key, 5.0)

    assert should_block_channel(key) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(("channel", "peer"), GROUP_IDS)
async def test_a_restart_recovers_the_spend_of_the_group(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, channel: str, peer: str
) -> None:
    msg = _group_message(channel, peer)
    await _spend_in_group(db_session, msg, 5.0)
    await save_channel_budget_policy(ChannelBudgetPolicy(channel_key=f"{channel}:group:{peer}", daily_limit_usd=1.0))

    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())
    await initialize_channel_budgets()

    assert should_block_channel(build_channel_budget_key(msg)) is True


@pytest.mark.asyncio
async def test_a_disabled_policy_is_still_listed_after_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    await update_channel_budget("telegram:group:g-1", ChannelBudgetPolicyRequest(enabled=False))

    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())
    await initialize_channel_budgets()

    listed = json.loads(bytes((await get_channel_budgets()).body))["data"]
    assert [(s["channel_key"], s["status"]) for s in listed["statuses"]] == [("telegram:group:g-1", "disabled")]
    assert should_block_channel("telegram:group:g-1") is False


@pytest.mark.asyncio
async def test_a_row_stored_with_raw_keys_is_listed_canonical_and_enforced(db_session: AsyncSession) -> None:
    await _store_raw_policies(db_session, ("slack:group:C024BE91L", 1.0), ("matrix:group:!abcdef:matrix.org", 1.0))

    listed = [policy.channel_key for policy in (await load_channel_budget_policies()).policies]
    await initialize_channel_budgets()

    assert listed == ["slack:group:c024be91l", "matrix:group:_abcdef_matrix_org"]
    for channel, peer in (("slack", "C024BE91L"), ("matrix", "!AbCdEf:matrix.org")):
        key = build_channel_budget_key(_group_message(channel, peer))
        record_channel_cost(key, 5.0)
        assert should_block_channel(key) is True


@pytest.mark.asyncio
async def test_policies_stored_under_two_spellings_become_one_on_the_next_write(db_session: AsyncSession) -> None:
    await _store_raw_policies(db_session, ("slack:group:C1", 5.0), ("Slack:group:c1", 1.0))

    await save_channel_budget_policy(ChannelBudgetPolicy(channel_key="telegram:group:g-1"))

    row = (await db_session.execute(select(UserConfig).where(UserConfig.config_key == CHANNEL_BUDGET_CONFIG_KEY))).scalar_one()
    assert [(p["channel_key"], p["daily_limit_usd"]) for p in row.config_value["policies"]] == [
        ("slack:group:c1", 1.0),
        ("telegram:group:g-1", 2.0),
    ]


@pytest.mark.asyncio
async def test_audit_and_delete_take_any_spelling_of_the_key(db_session: AsyncSession) -> None:
    msg = _group_message("slack", "C024BE91L")
    await update_channel_budget("slack:group:C024BE91L", _limit(1.0))
    await _spend_in_group(db_session, msg, 0.25)

    audit = json.loads(bytes((await get_channel_audit(" SLACK:group:c024be91l")).body))["data"]
    await delete_channel_budget("Slack:group:C024BE91L ")

    assert audit["channel_key"] == "slack:group:c024be91l"
    assert audit["total_cost_usd"] == pytest.approx(0.25)
    assert (await load_channel_budget_policies()).policies == []
    assert get_channel_budget_registry().get_status(build_channel_budget_key(msg)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["foo", "slack:dm:u1", "slack:group:"])
async def test_a_key_that_names_no_group_is_rejected_and_not_stored(key: str) -> None:
    with pytest.raises(StandardHTTPException) as rejected:
        await update_channel_budget(key, _limit(1.0))

    assert rejected.value.status_code == 400
    assert "<channel>:group:<chat id>" in str(rejected.value.detail)
    assert (await load_channel_budget_policies()).policies == []
