"""Unit tests for dev stack epoch reader."""

from __future__ import annotations

import json
from pathlib import Path

from app.server.stack_epoch import read_stack_epoch


def test_read_stack_epoch_missing_file_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MYRM_STACK_EPOCH_FILE", str(tmp_path / "missing.json"))
    assert read_stack_epoch() is None


def test_read_stack_epoch_valid_payload(tmp_path: Path, monkeypatch) -> None:
    epoch_file = tmp_path / "stack-epoch.json"
    epoch_file.write_text(
        json.dumps(
            {
                "epoch": 3,
                "backend_pid": 4242,
                "started_at": "2026-07-11T12:00:00Z",
                "harness_fingerprint": "source:/path/to/harness",
                "source_fingerprint": "deadbeef01234567",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_STACK_EPOCH_FILE", str(epoch_file))

    payload = read_stack_epoch()
    assert payload is not None
    assert payload["epoch"] == 3
    assert payload["backend_pid"] == 4242
    assert payload["started_at"] == "2026-07-11T12:00:00Z"
    assert payload["harness_fingerprint"] == "source:/path/to/harness"
    assert payload["source_fingerprint"] == "deadbeef01234567"


def test_read_stack_epoch_invalid_epoch_returns_none(
    tmp_path: Path, monkeypatch
) -> None:
    epoch_file = tmp_path / "stack-epoch.json"
    epoch_file.write_text(json.dumps({"epoch": 0}), encoding="utf-8")
    monkeypatch.setenv("MYRM_STACK_EPOCH_FILE", str(epoch_file))
    assert read_stack_epoch() is None
