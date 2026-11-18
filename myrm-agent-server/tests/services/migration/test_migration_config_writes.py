"""The settings the import confirm step writes reach the stored config the readers use.

Confirm edits three config rows: ``providers`` (model slots), ``mcpServers`` (migrated servers) and ``personalSettings``
(global instructions). Every test runs the real config service over a real in-memory database, so a call the service
refuses (no ``device_id``), a value the runtime cannot parse (the wrong ``mcpServers`` shape) and a row a writer must
not touch (one sealed under a key that is gone) fail here the way they fail for a user. The opt-in key import writes
``providers`` as well and is held to the same rules.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.config_parsers import extract_mcp_configs
from app.database.models import ConfigAuditLog, UserConfig
from app.services.config import service
from app.services.config.encryption import ConfigEncryptionService
from app.services.config.service import config_service
from app.services.memory.operations.crud.import_flows.instruction_lane import apply_instruction_lane
from app.services.memory.operations.crud.import_flows.side_effects import _write_migrated_mcp_configs
from app.services.migration.instruction_writer import (
    _replace_global_system_instructions,
    rollback_instruction_plan,
)
from app.services.migration.mcp_config_converter import convert_competitor_mcp_servers, mcp_migration_item_to_config_dict
from app.services.migration.source.source_migration_types import InstructionApplyResult, InstructionRollbackRecord
from app.services.migration.source.source_model_migrator import (
    migrate_hermes_auxiliary_models,
    migrate_openclaw_default_model,
)
from app.services.migration.source.source_secrets_importer import import_external_source_secrets
from tests.support.skill_credential_store import CredentialStore

MIGRATOR = "app.services.migration.source.source_model_migrator"
IMPORTER = "app.services.migration.source.source_secrets_importer"
DEVICE = "competitor-migration"
IMPORTED_KEY = "PLACEHOLDER_IMPORTED_KEY"

HERMES_AUXILIARY = {"auxiliary": {"vision": {"provider": "openrouter", "model": "google/gemini-2.5-flash"}}}
OPENCLAW_DEFAULTS = {"agents": {"defaults": {"model": "anthropic/claude-opus-4-6"}}}
OPENAI_ROW = {"id": "openai", "name": "openai", "isEnabled": True, "apiKeys": [{"id": "k1", "key": "sk-test", "isActive": True}]}
FS_SERVER = {"name": "fs", "type": "stdio", "command": "fs-server", "enabled": True}


@pytest.fixture(autouse=True)
def _local_install_without_process_privacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model migration runs on a local install; a ``personalSettings`` write republishes a process-wide policy."""
    monkeypatch.setattr(f"{MIGRATOR}.is_local_mode", lambda: True)
    monkeypatch.setattr("app.core.security.privacy_policy_sync.sync_privacy_policy", MagicMock())


async def _stored(key: str) -> dict[str, object]:
    record = await config_service.get(key)
    assert record is not None
    return record.value


def _entries(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]


async def _row(store: CredentialStore, key: str) -> tuple[dict[str, object], str]:
    """The row as the database holds it (sealed values stay sealed) with its version."""
    async with store.sessions() as db:
        row = (await db.execute(select(UserConfig).where(UserConfig.config_key == key))).scalar_one()
        return copy.deepcopy(row.config_value), row.version


async def _writers(store: CredentialStore, key: str) -> set[str]:
    async with store.sessions() as db:
        rows = (await db.execute(select(ConfigAuditLog).where(ConfigAuditLog.config_key == key))).scalars().all()
        return {row.device_id for row in rows}


def _rollback_record(previous_global_instructions: str) -> InstructionRollbackRecord:
    return InstructionRollbackRecord(
        target_agent_id="agent-1",
        profile_snapshot_id=None,
        previous_global_instructions=previous_global_instructions,
        global_instructions_updated=True,
        written_rule_paths=(),
        competitor="",
    )


def _lose_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Seal-key loss: rows written so far can no longer be opened."""
    other = ConfigEncryptionService(encryption_key=os.urandom(32), is_sandbox=False, is_local=True)
    monkeypatch.setattr(service, "get_encryption_service", lambda: other)


# --- model slots (providers) -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hermes_auxiliary_models_are_written_to_a_fresh_install(credentials: CredentialStore) -> None:
    result = await migrate_hermes_auxiliary_models(copy.deepcopy(HERMES_AUXILIARY))

    assert result.migrated_slots == {"visionFallbackModel": "google/gemini-2.5-flash"}
    default_models = (await _stored("providers"))["defaultModelConfig"]
    assert isinstance(default_models, dict)
    assert default_models["visionFallbackModel"] == {"model": "google/gemini-2.5-flash"}
    assert await _writers(credentials, "providers") == {DEVICE}


@pytest.mark.asyncio
async def test_the_openclaw_default_model_is_merged_into_the_stored_providers(credentials: CredentialStore) -> None:
    await credentials.store_providers([OPENAI_ROW], default_model=False)

    assert await migrate_openclaw_default_model(copy.deepcopy(OPENCLAW_DEFAULTS)) == "anthropic/claude-opus-4-6"

    stored = await _stored("providers")
    assert [row["id"] for row in _entries(stored["providers"])] == ["openai"]
    assert stored["defaultModelConfig"] == {
        "baseModel": {"primary": {"providerId": "anthropic", "model": "claude-opus-4-6"}},
    }
    assert DEVICE in await _writers(credentials, "providers")


@pytest.mark.asyncio
async def test_providers_sealed_under_a_lost_key_are_left_as_they_are(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    await credentials.store_providers([OPENAI_ROW], default_model=False)
    before = await _row(credentials, "providers")
    _lose_the_key(monkeypatch)

    assert await migrate_openclaw_default_model(copy.deepcopy(OPENCLAW_DEFAULTS)) is None
    assert (await migrate_hermes_auxiliary_models(copy.deepcopy(HERMES_AUXILIARY))).migrated_slots == {}

    # Writing over the empty value of a row that cannot be opened would destroy ciphertext the user can still restore.
    assert await _row(credentials, "providers") == before


# --- the opt-in key import (providers) ---------------------------------------------------------------------------


def _dotenv_root(root: Path) -> Path:
    (root / ".env").write_text(f"OPENAI_API_KEY={IMPORTED_KEY}\n", encoding="utf-8")
    return root


@pytest.mark.asyncio
async def test_an_imported_key_lands_in_a_new_provider_row(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(f"{IMPORTER}.is_local_mode", lambda: True)

    result = await import_external_source_secrets(_dotenv_root(tmp_path))

    assert result.imported_keys == ["OPENAI_API_KEY"]
    [row] = _entries((await _stored("providers"))["providers"])
    assert row["id"] == "openai"
    assert [entry["key"] for entry in _entries(row["apiKeys"])] == [IMPORTED_KEY]
    assert await _writers(credentials, "providers") == {DEVICE}


@pytest.mark.asyncio
async def test_the_key_import_leaves_providers_sealed_under_a_lost_key_alone(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    await credentials.store_providers([OPENAI_ROW], default_model=False)
    before = await _row(credentials, "providers")
    _lose_the_key(monkeypatch)
    monkeypatch.setattr(f"{IMPORTER}.is_local_mode", lambda: True)

    with pytest.raises(ValueError, match="cannot be decrypted"):
        await import_external_source_secrets(_dotenv_root(tmp_path))

    assert await _row(credentials, "providers") == before


# --- migrated MCP servers (mcpServers) ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrated_mcp_servers_join_the_stored_list_disabled(credentials: CredentialStore) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(FS_SERVER)]}, device_id="web")

    inserted = await _write_migrated_mcp_configs(
        [
            {"name": "fs", "type": "stdio", "command": "other"},
            {"name": " "},
            {"name": "db", "type": "stdio", "command": "db-server"},
        ],
    )

    assert inserted == 1
    stored = await _stored("mcpServers")
    assert stored == {"mcpConfigs": [FS_SERVER, {"name": "db", "type": "stdio", "command": "db-server", "enabled": False}]}
    # The runtime reads the ``mcpConfigs`` list and starts only what is enabled: the user's server stays, the new one waits.
    assert [cfg.name for cfg in extract_mcp_configs(stored)] == ["fs"]
    assert DEVICE in await _writers(credentials, "mcpServers")


@pytest.mark.asyncio
async def test_a_migrated_mcp_server_starts_once_the_user_enables_it(credentials: CredentialStore) -> None:
    converted = convert_competitor_mcp_servers(
        {"github": {"command": "npx", "args": ["-y", "server-github"], "env": {"GITHUB_PAT": "PLACEHOLDER_MCP_CREDENTIAL"}}},
        competitor="claude",
    )

    inserted = await _write_migrated_mcp_configs([mcp_migration_item_to_config_dict(item) for item in converted])

    stored = await _stored("mcpServers")
    assert inserted == 1
    assert "PLACEHOLDER_MCP_CREDENTIAL" not in str(stored)
    migrated = _entries(stored["mcpConfigs"])[0]
    assert extract_mcp_configs(stored) == []
    enabled = {**stored, "mcpConfigs": [{**migrated, "enabled": True}]}
    assert [(cfg.name, cfg.type, cfg.command) for cfg in extract_mcp_configs(enabled)] == [("github", "stdio", "npx")]


@pytest.mark.asyncio
async def test_other_keys_of_the_stored_mcp_config_survive_the_write(credentials: CredentialStore) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [], "layout": "grid"}, device_id="web")

    assert await _write_migrated_mcp_configs([{"name": "db", "type": "stdio", "command": "db-server"}]) == 1

    assert (await _stored("mcpServers"))["layout"] == "grid"


@pytest.mark.asyncio
async def test_nothing_is_written_when_every_migrated_server_is_already_there(credentials: CredentialStore) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(FS_SERVER)]}, device_id="web")
    before = await _row(credentials, "mcpServers")

    assert await _write_migrated_mcp_configs([{"name": "fs", "type": "stdio", "command": "other"}]) == 0

    assert await _row(credentials, "mcpServers") == before


@pytest.mark.asyncio
async def test_mcp_servers_sealed_under_a_lost_key_are_left_as_they_are(
    credentials: CredentialStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    await config_service.set("mcpServers", {"mcpConfigs": [copy.deepcopy(FS_SERVER)]}, device_id="web")
    before = await _row(credentials, "mcpServers")
    _lose_the_key(monkeypatch)

    assert await _write_migrated_mcp_configs([{"name": "db", "type": "stdio", "command": "db-server"}]) == 0

    assert await _row(credentials, "mcpServers") == before


# --- global instructions (personalSettings) ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_supplement_is_merged_into_the_stored_global_instructions(credentials: CredentialStore) -> None:
    await config_service.set("personalSettings", {"systemInstructions": "Answer in French.", "theme": "dark"}, device_id="web")

    previous, updated = await _replace_global_system_instructions("Prefer small diffs.", "claude")

    assert (previous, updated) == ("Answer in French.", True)
    stored = await _stored("personalSettings")
    assert stored["theme"] == "dark"
    instructions = str(stored["systemInstructions"])
    assert instructions.startswith("Answer in French.")
    assert "Prefer small diffs." in instructions
    assert DEVICE in await _writers(credentials, "personalSettings")


@pytest.mark.asyncio
async def test_a_second_import_replaces_the_block_of_the_same_source(credentials: CredentialStore) -> None:
    await config_service.set("personalSettings", {"systemInstructions": "Answer in French."}, device_id="web")

    await _replace_global_system_instructions("First supplement.", "claude")
    await _replace_global_system_instructions("Second supplement.", "claude")

    instructions = str((await _stored("personalSettings"))["systemInstructions"])
    assert "Second supplement." in instructions
    assert "First supplement." not in instructions
    assert instructions.startswith("Answer in French.")


@pytest.mark.asyncio
async def test_no_personal_settings_row_means_no_global_instruction_write(credentials: CredentialStore) -> None:
    assert await _replace_global_system_instructions("Prefer small diffs.", "claude") == ("", False)

    assert await config_service.get("personalSettings") is None


@pytest.mark.asyncio
async def test_rolling_back_restores_the_previous_global_instructions(credentials: CredentialStore) -> None:
    await config_service.set("personalSettings", {"systemInstructions": "Answer in French.", "theme": "dark"}, device_id="web")
    previous, _ = await _replace_global_system_instructions("Prefer small diffs.", "claude")

    restored = await rollback_instruction_plan(_rollback_record(previous))

    assert restored is True
    assert await _stored("personalSettings") == {"systemInstructions": "Answer in French.", "theme": "dark"}
    assert DEVICE in await _writers(credentials, "personalSettings")


# --- the readers see the write -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_rollback_is_seen_by_the_next_config_load(credentials: CredentialStore) -> None:
    await credentials.store_providers([OPENAI_ROW])
    await config_service.set("personalSettings", {"systemInstructions": "Answer in French."}, device_id="web")
    previous, _ = await _replace_global_system_instructions("Prefer small diffs.", "claude")
    # A turn after the import loaded the merged instructions, and the loader keeps what it loaded for a while.
    assert "Prefer small diffs." in str((await load_user_configs()).personal_settings_dict)

    await rollback_instruction_plan(_rollback_record(previous))

    assert (await load_user_configs()).personal_settings_dict == {"systemInstructions": "Answer in French."}


@pytest.mark.asyncio
async def test_the_confirm_lane_writes_are_seen_by_the_next_config_load(credentials: CredentialStore) -> None:
    await credentials.store_providers([OPENAI_ROW])
    assert (await load_user_configs()).mcp_dict is None
    applied = InstructionApplyResult(
        target_agent_id="agent-1",
        agent_created=False,
        global_instructions_updated=False,
        workspace_rules_written=0,
    )

    with (
        patch("app.services.migration.instruction_writer.apply_instruction_plan", AsyncMock(return_value=applied)),
        patch("app.services.memory.imports.import_ledger.MemoryImportLedgerService.merge_batch_metadata", AsyncMock()),
    ):
        outcome = await apply_instruction_lane(
            cast(AsyncSession, SimpleNamespace()),
            import_batch_id="memory-import-batch:test",
            raw_plan={"competitor": "claude", "mcp_configs": [{"name": "db", "type": "stdio", "command": "db-server"}]},
            raw_options={},
            metadata={"model_migration": {"hermes_auxiliary": copy.deepcopy(HERMES_AUXILIARY["auxiliary"])}},
            workspace_root=None,
        )

    configs = await load_user_configs()
    assert outcome.mcp_imported_disabled_count == 1
    assert [cfg["name"] for cfg in _entries((configs.mcp_dict or {}).get("mcpConfigs"))] == ["db"]
    default_models = (configs.providers_dict or {}).get("defaultModelConfig")
    assert isinstance(default_models, dict)
    assert default_models["visionFallbackModel"] == {"model": "google/gemini-2.5-flash"}
