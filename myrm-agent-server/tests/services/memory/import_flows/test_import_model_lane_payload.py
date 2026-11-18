"""The model lane of a review session keeps only the fields confirm replays.

A competitor config block also carries credentials (a per-task ``api_key``, the memory-search
key under ``agents.defaults``). The persisted review session and the replayed migration must
see none of them, and replaying must produce the settings the raw block would have produced.
"""

from __future__ import annotations

import copy
import json
from typing import cast
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config.service import config_service
from app.services.memory.operations.crud.import_flows.dry_run_source import (
    LoadedSource,
    SideChannels,
    build_session_metadata,
    build_side_channels,
)
from app.services.memory.operations.crud.import_flows.side_effects import _apply_model_migration
from app.services.migration.source.source_migration_types import (
    MigrationWizardOptions,
    SourceInstructionPlan,
)
from tests.services.memory.import_flows.support import persisted_review_session, stored_columns_text
from tests.support.skill_credential_store import credential_store

CREDENTIAL = "PLACEHOLDER_MODEL_LANE_CREDENTIAL"
MIGRATOR = "app.services.migration.source.source_model_migrator"


def _hermes_auxiliary() -> dict[str, object]:
    return {
        "vision": {
            "provider": "openrouter",
            "model": "google/gemini-2.5-flash",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key": CREDENTIAL,
            "timeout": 30,
        },
        "compression": {"provider": "main", "model": "gpt-4o-mini"},
        "title_generation": {"provider": "openai", "model": ""},
    }


def _openclaw_defaults() -> dict[str, object]:
    return {
        "model": "opus",
        "models": {"anthropic/claude-opus-4-6": {"alias": "opus"}},
        "memorySearch": {"remote": {"baseUrl": "http://127.0.0.1:9/v1", "apiKey": CREDENTIAL}},
    }


def _hermes_config() -> dict[str, object]:
    return {"auxiliary": _hermes_auxiliary()}


def _openclaw_config() -> dict[str, object]:
    return {"agents": {"defaults": _openclaw_defaults()}}


def _loaded(loaded_payload: dict[str, object]) -> LoadedSource:
    return LoadedSource(
        loaded_payload=loaded_payload,
        instruction_plan=SourceInstructionPlan(competitor="hermes"),
        migration_opts=MigrationWizardOptions(),
        import_payload={},
        resolved_source="hermes",
        competitor="hermes",
        source_has_api_keys=False,
        secrets_importable=False,
        pending_skills=[],
        pending_skills_total=0,
        coverage_items=[],
    )


def _side_channels(loaded: LoadedSource) -> SideChannels:
    with patch(
        "app.services.migration.workspace_bind_candidates.discover_workspace_bind_candidates",
        return_value=[],
    ):
        return build_side_channels(loaded)


async def _replay(monkeypatch: pytest.MonkeyPatch, model_data: dict[str, object]) -> dict[str, object]:
    """Run the confirm-side model migration on a fresh install and return the providers config it stored."""

    async with credential_store(monkeypatch):
        monkeypatch.setattr(f"{MIGRATOR}.is_local_mode", lambda: True)
        await _apply_model_migration(copy.deepcopy(model_data))
        record = await config_service.get("providers")
    assert record is not None
    return record.value


def test_the_hermes_lane_keeps_the_provider_model_pairs_confirm_replays() -> None:
    channels = _side_channels(_loaded({"hermes_config": _hermes_config()}))

    assert channels.model_migration_payload == {
        "hermes_auxiliary": {
            "vision": {"provider": "openrouter", "model": "google/gemini-2.5-flash"},
            "compression": {"provider": "auto", "model": "gpt-4o-mini"},
        },
    }
    assert CREDENTIAL not in json.dumps(channels.model_migration_payload)


def test_the_openclaw_lane_keeps_the_default_model_and_alias_catalog_only() -> None:
    channels = _side_channels(_loaded({"openclaw_config": _openclaw_config()}))

    assert channels.model_migration_payload == {
        "openclaw_agents_defaults": {
            "model": "opus",
            "models": {"anthropic/claude-opus-4-6": {"alias": "opus"}},
        },
    }
    assert CREDENTIAL not in json.dumps(channels.model_migration_payload)


@pytest.mark.parametrize(
    "loaded_payload",
    [
        {"hermes_config": {"auxiliary": {"vision": {"provider": "openai", "model": "", "api_key": CREDENTIAL}}}},
        {"openclaw_config": {"agents": {"defaults": {"memorySearch": {"remote": {"apiKey": CREDENTIAL}}}}}},
        {"openclaw_config": {"agents": ["not-a-mapping"]}},
        {"openclaw_config": {"agents": {"defaults": "not-a-mapping"}}},
    ],
    ids=["hermes-without-model", "openclaw-without-model", "agents-not-a-mapping", "defaults-not-a-mapping"],
)
def test_a_source_without_a_replayable_model_leaves_the_lane_out(loaded_payload: dict[str, object]) -> None:
    loaded = _loaded(loaded_payload)
    channels = _side_channels(loaded)

    metadata = build_session_metadata(loaded, channels, providers_configured=False)

    assert channels.model_migration_payload == {}
    assert "model_migration" not in metadata
    assert CREDENTIAL not in json.dumps(metadata)


@pytest.mark.asyncio
async def test_replaying_the_reduced_lane_migrates_what_the_raw_blocks_would(monkeypatch: pytest.MonkeyPatch) -> None:
    raw: dict[str, object] = {"hermes_auxiliary": _hermes_auxiliary(), "openclaw_agents_defaults": _openclaw_defaults()}
    channels = _side_channels(_loaded({"hermes_config": _hermes_config(), "openclaw_config": _openclaw_config()}))

    reduced = await _replay(monkeypatch, channels.model_migration_payload)
    from_raw = await _replay(monkeypatch, raw)

    assert reduced == from_raw
    default_models = cast("dict[str, object]", reduced["defaultModelConfig"])
    assert default_models["visionFallbackModel"] == {"model": "google/gemini-2.5-flash"}
    assert default_models["baseModel"] == {"primary": {"providerId": "anthropic", "model": "claude-opus-4-6"}}


@pytest.mark.parametrize(
    ("competitor", "config_key", "config", "memory"),
    [
        ("hermes", "hermes_config", _hermes_config(), {"memory_md": "Prefers small diffs."}),
        ("openclaw", "openclaw_config", _openclaw_config(), {"openclaw_memory": [{"content": "Prefers small diffs."}]}),
    ],
)
@pytest.mark.asyncio
async def test_the_persisted_review_session_holds_no_model_lane_credential(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    competitor: str,
    config_key: str,
    config: dict[str, object],
    memory: dict[str, object],
) -> None:
    row = await persisted_review_session(db_session, competitor, {config_key: config, **memory})

    assert CREDENTIAL not in stored_columns_text(row)

    model_migration = (row.metadata_json or {})["model_migration"]
    assert isinstance(model_migration, dict)
    replayed = await _replay(monkeypatch, model_migration)
    assert replayed["defaultModelConfig"]
