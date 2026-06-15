"""Architecture test: migration wizard discover probes == loaders == closed set."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.migration import competitor_probes
from app.services.migration.competitor_payload_loader import (
    load_competitor_payload,
    supported_competitor_ids,
)


def _discover_probe_ids() -> frozenset[str]:
    ids: set[str] = set()
    for name in dir(competitor_probes):
        if not name.startswith("discover_"):
            continue
        fn = getattr(competitor_probes, name)
        if callable(fn) and fn.__module__ == competitor_probes.__name__:
            ids.add(name.removeprefix("discover_"))
    return frozenset(ids)


@pytest.mark.architecture
def test_migration_probe_ids_match_supported_competitor_ids() -> None:
    closed = supported_competitor_ids()
    probe_ids = _discover_probe_ids()
    assert probe_ids == closed, f"probe/closed drift: probes={probe_ids} closed={closed}"


@pytest.mark.architecture
def test_migration_loaders_registered_for_all_supported_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.migration.competitor_payload_loader.is_local_mode",
        lambda: True,
    )
    closed = supported_competitor_ids()
    for competitor_id in closed:
        root = tmp_path / competitor_id
        root.mkdir()
        loaded = load_competitor_payload(
            {"competitor": competitor_id, "root": str(root), "files": []},
        )
        assert loaded.get("_load_error") is None, f"loader missing for {competitor_id!r}"


@pytest.mark.architecture
def test_migration_loaders_reject_unknown_competitor_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.migration.competitor_payload_loader.is_local_mode",
        lambda: True,
    )
    loaded = load_competitor_payload(
        {"competitor": "unknown_vendor", "root": str(tmp_path), "files": []},
    )
    assert loaded.get("_load_error") is not None
