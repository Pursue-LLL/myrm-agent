"""Tests for migration source manifest SSOT helpers."""

from __future__ import annotations

from app.services.migration.source_manifest import (
    migration_source_deep_link_ids,
    migration_source_import_map,
    migration_source_local_scan_ids,
    migration_source_manifest_authoritative,
    migration_source_manifest_authoritative_for_ids,
    migration_source_manifest_entries,
    migration_source_manifest_ids,
    migration_source_manifest_payload,
)
from app.services.migration.source_payload_loader import supported_source_ids


def test_manifest_ids_match_expected_sources() -> None:
    ids = [item.id for item in migration_source_manifest_entries()]
    assert ids == ["hermes", "openclaw", "claude", "codex", "chatgpt", "gbrain", "pi"]


def test_local_scan_ids_match_loader_closed_set() -> None:
    assert migration_source_local_scan_ids() == supported_source_ids()


def test_import_map_covers_upload_only_chatgpt() -> None:
    mapping = migration_source_import_map()
    assert mapping["chatgpt"] == "chatgpt"
    assert mapping["hermes"] == "hermes"
    assert mapping["claude"] == "claude"


def test_manifest_payload_is_json_safe() -> None:
    payload = migration_source_manifest_payload()
    assert len(payload) == 7
    assert payload[0]["id"] == "hermes"
    assert payload[-1]["id"] == "pi"
    assert payload[-1]["discover_modes"] == ["local_scan"]


def test_deep_link_ids_include_all_manifest_sources() -> None:
    assert migration_source_deep_link_ids() == {"hermes", "openclaw", "claude", "codex", "chatgpt", "gbrain", "pi"}


def test_manifest_is_authoritative_for_frontend_consumers() -> None:
    assert migration_source_manifest_authoritative() is True


def test_authoritative_guard_requires_full_manifest_id_coverage() -> None:
    assert migration_source_manifest_authoritative_for_ids(migration_source_manifest_ids()) is True
    assert migration_source_manifest_authoritative_for_ids({"hermes", "openclaw"}) is False
