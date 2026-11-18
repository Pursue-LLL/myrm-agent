"""A review session keeps the settings of a source without the credentials in them.

A settings file (Claude's ``env`` block, a Codex or Pi ``apiKey``) is shown to the model as part of the global
instructions the confirm step applies, and the review session that carries it to confirm is stored. Neither may hold a
credential, and the settings that are no credential must still be there.
"""

from __future__ import annotations

import copy
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryImportDryRunModel
from app.services.config.service import config_service
from app.services.memory.operations.crud.import_flows.instruction_lane import plan_from_metadata
from app.services.migration.instruction_writer import _replace_global_system_instructions
from tests.services.memory.import_flows.support import persisted_review_session, stored_columns_text
from tests.support.skill_credential_store import CredentialStore

CREDENTIAL = "PLACEHOLDER_SETTINGS_LANE_CREDENTIAL"

SETTINGS_SOURCES = [
    (
        "claude",
        "claude_settings",
        {"model": "opus", "env": {"ANTHROPIC_AUTH_TOKEN": CREDENTIAL, "ANTHROPIC_BASE_URL": "https://gateway.example.test"}},
        '"model": "opus"',
    ),
    (
        "codex",
        "codex_settings",
        {"model": "o3", "providers": {"openai": {"apiKey": CREDENTIAL}}},
        '"model": "o3"',
    ),
    (
        "pi",
        "pi_settings",
        {"defaultProvider": "anthropic", "apiKey": CREDENTIAL},
        '"defaultProvider": "anthropic"',
    ),
]
SETTINGS_COLUMNS = ("competitor", "settings_key", "settings", "kept")


def _stored_instruction_plan(row: MemoryImportDryRunModel) -> dict[str, object]:
    instruction_plan = (row.metadata_json or {})["instruction_plan"]
    assert isinstance(instruction_plan, dict)
    return instruction_plan


@pytest.mark.parametrize(SETTINGS_COLUMNS, SETTINGS_SOURCES)
@pytest.mark.asyncio
async def test_the_persisted_review_session_holds_no_settings_credential(
    db_session: AsyncSession,
    competitor: str,
    settings_key: str,
    settings: dict[str, object],
    kept: str,
) -> None:
    row = await persisted_review_session(
        db_session,
        competitor,
        {settings_key: copy.deepcopy(settings), "memory_md": "Prefers small diffs."},
    )

    assert CREDENTIAL not in stored_columns_text(row)
    supplement = str(_stored_instruction_plan(row)["global_supplement"])
    assert "settings (from" in supplement
    assert kept in supplement


@pytest.mark.parametrize(SETTINGS_COLUMNS, SETTINGS_SOURCES)
@pytest.mark.asyncio
async def test_the_global_instructions_confirm_stores_hold_no_settings_credential(
    db_session: AsyncSession,
    credentials: CredentialStore,
    monkeypatch: pytest.MonkeyPatch,
    competitor: str,
    settings_key: str,
    settings: dict[str, object],
    kept: str,
) -> None:
    monkeypatch.setattr("app.core.security.privacy_policy_sync.sync_privacy_policy", MagicMock())
    row = await persisted_review_session(
        db_session,
        competitor,
        {settings_key: copy.deepcopy(settings), "memory_md": "Prefers small diffs."},
    )
    plan = plan_from_metadata(_stored_instruction_plan(row))
    await config_service.set("personalSettings", {"systemInstructions": "Answer in French."}, device_id="web")

    _, updated = await _replace_global_system_instructions(plan.global_supplement, plan.competitor)

    record = await config_service.get("personalSettings")
    assert updated is True
    assert record is not None
    instructions = str(record.value["systemInstructions"])
    assert instructions.startswith("Answer in French.")
    assert kept in instructions
    assert CREDENTIAL not in instructions
