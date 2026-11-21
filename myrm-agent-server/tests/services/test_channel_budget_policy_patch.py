"""A channel budget edit changes the fields it names and nothing else.

The settings page sends each edit as it was made, from the policy it last loaded, and a second page or device may have
changed other fields of that policy since. An edit that carried the whole policy would put those fields back (a lowered
limit raised again, a deleted channel brought back); a patch leaves them alone, in the stored policy and in the budget
that is enforced. Real SQLite and the real budget API handlers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import NoReturn

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.budget.router import (
    ChannelBudgetPolicyRequest,
    delete_channel_budget,
    patch_channel_budget,
    update_channel_budget,
)
from app.core.utils.errors import StandardHTTPException
from app.services.budget import channel_budget
from app.services.budget.channel_budget import (
    ChannelBudgetRegistry,
    get_channel_budget_registry,
    load_channel_budget_policies,
    record_channel_cost,
    should_block_channel,
)
from app.services.budget.channel_budget_policy import ChannelBudgetPolicy, ChannelBudgetPolicyPatch
from tests.support.channel_budget_fixtures import budget_database

KEY = "telegram:group:g-1"


@pytest.fixture(autouse=True)
def _database(db_session: AsyncSession) -> Iterator[None]:
    with budget_database(db_session):
        yield


@pytest.fixture(autouse=True)
def _registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_budget, "_registry", ChannelBudgetRegistry())


def _limit(usd: float) -> ChannelBudgetPolicyRequest:
    return ChannelBudgetPolicyRequest(daily_limit_usd=usd)


async def _stored() -> dict[str, ChannelBudgetPolicy]:
    return {policy.channel_key: policy for policy in (await load_channel_budget_policies()).policies}


def _spent() -> object:
    status = get_channel_budget_registry().get_status(KEY)
    assert status is not None
    return status["today_cost_usd"]


@pytest.mark.asyncio
async def test_a_patch_changes_only_the_fields_it_names() -> None:
    await update_channel_budget(KEY, ChannelBudgetPolicyRequest(daily_limit_usd=5.0, warning_threshold=0.6, label="Team chat"))

    response = await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(enabled=False))

    expected = {"channel_key": KEY, "daily_limit_usd": 5.0, "warning_threshold": 0.6, "enabled": False, "label": "Team chat"}
    assert json.loads(bytes(response.body))["data"] == expected
    assert (await _stored())[KEY].model_dump() == expected


@pytest.mark.asyncio
async def test_a_patch_from_a_stale_page_keeps_the_limit_another_page_set() -> None:
    await update_channel_budget(KEY, _limit(5.0))
    await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(daily_limit_usd=1.0))  # another device lowers the limit

    await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(warning_threshold=0.5))  # this page still shows a limit of 5

    stored = (await _stored())[KEY]
    assert (stored.daily_limit_usd, stored.warning_threshold) == (1.0, 0.5)
    record_channel_cost(KEY, 3.0)
    assert should_block_channel(KEY) is True


@pytest.mark.asyncio
async def test_a_patch_of_a_policy_deleted_meanwhile_is_not_found_and_brings_nothing_back() -> None:
    await update_channel_budget(KEY, _limit(5.0))
    await delete_channel_budget(KEY)

    with pytest.raises(StandardHTTPException) as missing:
        await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(enabled=False))

    assert missing.value.status_code == 404
    assert await _stored() == {}
    assert get_channel_budget_registry().get_status(KEY) is None


@pytest.mark.asyncio
async def test_a_patch_takes_effect_on_the_budget_being_enforced() -> None:
    await update_channel_budget(KEY, _limit(100.0))

    await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(daily_limit_usd=1.0))
    record_channel_cost(KEY, 5.0)
    assert should_block_channel(KEY) is True

    await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(enabled=False))
    assert should_block_channel(KEY) is False


@pytest.mark.asyncio
async def test_a_patch_keeps_the_cost_a_turn_added_after_the_spend_was_read(monkeypatch: pytest.MonkeyPatch) -> None:
    await update_channel_budget(KEY, _limit(5.0))
    read_spend = channel_budget._query_channel_today_cost

    async def read_spend_then_finish_a_turn(channel_key: str) -> float:
        spent = await read_spend(channel_key)
        record_channel_cost(KEY, 0.7)  # stored and counted after the spend was read, before the edit is written
        return spent

    monkeypatch.setattr(channel_budget, "_query_channel_today_cost", read_spend_then_finish_a_turn)

    await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(daily_limit_usd=3.0))

    assert _spent() == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_a_patch_keeps_the_cost_when_the_spend_cannot_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    await update_channel_budget(KEY, _limit(5.0))
    record_channel_cost(KEY, 0.7)

    def unreadable_day_start(days_ago: int = 0) -> NoReturn:
        raise OSError("the spend cannot be read")

    monkeypatch.setattr(channel_budget, "budget_day_start_utc", unreadable_day_start)

    await patch_channel_budget(KEY, ChannelBudgetPolicyPatch(daily_limit_usd=3.0))

    assert _spent() == pytest.approx(0.7)


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [{"daily_limit_usd": 0.0}, {"warning_threshold": 2.0}, {"daily_limit_usd": None}])
async def test_a_patch_with_an_invalid_value_is_rejected_and_stores_nothing(fields: dict[str, float | None]) -> None:
    await update_channel_budget(KEY, _limit(5.0))

    with pytest.raises(StandardHTTPException) as rejected:
        await patch_channel_budget(KEY, ChannelBudgetPolicyPatch.model_validate(fields))

    assert rejected.value.status_code == 400
    assert (await _stored())[KEY] == ChannelBudgetPolicy(channel_key=KEY, daily_limit_usd=5.0)


def test_a_patch_may_not_name_a_field_a_policy_does_not_have() -> None:
    with pytest.raises(ValidationError):
        ChannelBudgetPolicyPatch.model_validate({"channel_key": "slack:group:c1"})


@pytest.mark.asyncio
async def test_a_patch_takes_any_spelling_of_the_key() -> None:
    await update_channel_budget("slack:group:C024BE91L", _limit(5.0))

    await patch_channel_budget(" SLACK:group:c024be91l ", ChannelBudgetPolicyPatch(label="Ops"))

    assert [(key, policy.label) for key, policy in (await _stored()).items()] == [("slack:group:c024be91l", "Ops")]


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["foo", "slack:dm:u1", "slack:group:"])
async def test_a_patch_to_a_key_that_names_no_group_is_rejected(key: str) -> None:
    with pytest.raises(StandardHTTPException) as rejected:
        await patch_channel_budget(key, ChannelBudgetPolicyPatch(enabled=False))

    assert rejected.value.status_code == 400
    assert "<channel>:group:<chat id>" in str(rejected.value.detail)
