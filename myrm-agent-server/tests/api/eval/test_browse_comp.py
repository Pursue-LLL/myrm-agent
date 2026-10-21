"""Unit tests for the BrowseComp adapter.

Covers the canary XOR decryption, catalog entry, case building from a local
CSV, download no-op when already installed, and registry registration.
Network access is mocked so tests run fully offline.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.core.eval import browse_comp as bc


@pytest.fixture(autouse=True)
def _isolate_browsecomp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point BrowseComp storage at a temp dir for every test."""
    monkeypatch.setattr(bc, "BROWSECOMP_ROOT", tmp_path / "browsecomp")
    monkeypatch.setattr(bc, "BROWSECOMP_CSV", tmp_path / "browsecomp" / "browse_comp_test_set.csv")
    yield


def _encrypt(plaintext: str, canary: str) -> str:
    """Encrypt a plaintext field with the same canary XOR scheme as _decrypt."""
    data = plaintext.encode("utf-8")
    digest = hashlib.sha256(canary.encode("utf-8")).digest()
    key = (digest * (len(data) // len(digest) + 1))[: len(data)]
    return base64.b64encode(bytes(a ^ b for a, b in zip(data, key, strict=True))).decode("ascii")


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["canary", "problem", "answer", "problem_topic"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_decrypt_roundtrip() -> None:
    """_decrypt inverts the official canary XOR encryption."""
    canary = "example canary value"
    plaintext = "What is the tallest building in the world?"
    encrypted = _encrypt(plaintext, canary)
    assert bc._decrypt(encrypted, canary) == plaintext


def test_list_browse_comp_source_not_downloaded() -> None:
    """Catalog entry reports not-downloaded with zero local size."""
    entry = bc.list_browse_comp_source()
    assert entry["id"] == "browsecomp"
    assert entry["name"] == "BrowseComp"
    assert entry["scoring"] == "llm_judge"
    assert entry["is_downloaded"] is False
    assert entry["local_size_bytes"] == 0


def test_list_browse_comp_source_downloaded() -> None:
    """Catalog entry reports the local file size once downloaded."""
    bc.BROWSECOMP_CSV.parent.mkdir(parents=True, exist_ok=True)
    bc.BROWSECOMP_CSV.write_text("canary,problem,answer,problem_topic\n")
    entry = bc.list_browse_comp_source()
    assert entry["is_downloaded"] is True
    assert entry["local_size_bytes"] > 0


def test_ensure_browse_comp_source_noop_when_installed() -> None:
    """Download is skipped when the CSV already exists (offline-friendly)."""
    bc.BROWSECOMP_CSV.parent.mkdir(parents=True, exist_ok=True)
    bc.BROWSECOMP_CSV.write_text("canary,problem,answer,problem_topic\n")
    with patch.object(bc, "_fetch_expected_sha256", new=AsyncMock()) as fetch:
        result = _run(bc.ensure_browse_comp_source())
        assert result == bc.BROWSECOMP_CSV
        fetch.assert_not_awaited()


def test_build_browse_comp_cases_builds_tasks() -> None:
    """Case building decrypts rows and emits one MultiTurnEvalCase per task."""
    canary = "canary-A"
    _write_csv(
        bc.BROWSECOMP_CSV,
        [
            {
                "canary": canary,
                "problem": _encrypt("Research question A?", canary),
                "answer": _encrypt("Reference answer A.", canary),
                "problem_topic": "science",
            },
            {
                "canary": canary,
                "problem": _encrypt("Research question B?", canary),
                "answer": _encrypt("Reference answer B.", canary),
                "problem_topic": "",
            },
        ],
    )
    with patch.object(bc, "ensure_browse_comp_source", new=AsyncMock()):
        cases, seed_map = bc.build_browse_comp_cases()

    assert seed_map == {}
    assert len(cases) == 2
    turn = cases[0].turns[0]
    assert turn.message == "Research question A?"
    assert len(turn.semantic_assertions) == 1
    assertion = turn.semantic_assertions[0]
    assert assertion.type == "llm_judge"
    assert "Research question A?" in assertion.expected
    assert "Reference answer A." in assertion.expected
    assert cases[0].turns[0].metadata.get("problem_topic") == "science"
    assert "problem_topic" not in cases[1].turns[0].metadata


def test_build_browse_comp_cases_skips_malformed_rows() -> None:
    """Rows missing canary/problem/answer are skipped."""
    _write_csv(
        bc.BROWSECOMP_CSV,
        [
            {
                "canary": "",
                "problem": "no canary",
                "answer": "no canary",
                "problem_topic": "",
            },
        ],
    )
    with patch.object(bc, "ensure_browse_comp_source", new=AsyncMock()):
        with pytest.raises(ValueError, match="No runnable BrowseComp tasks found"):
            bc.build_browse_comp_cases()


def test_build_browse_comp_cases_skips_undecryptable_rows() -> None:
    """A row with an undecryptable payload is skipped, not fatal."""
    canary = "canary-A"
    _write_csv(
        bc.BROWSECOMP_CSV,
        [
            {
                "canary": canary,
                "problem": "not-base64!!",
                "answer": _encrypt("Reference answer.", canary),
                "problem_topic": "",
            },
            {
                "canary": canary,
                "problem": _encrypt("Research question B?", canary),
                "answer": _encrypt("Reference answer B.", canary),
                "problem_topic": "",
            },
        ],
    )
    with patch.object(bc, "ensure_browse_comp_source", new=AsyncMock()):
        cases, seed_map = bc.build_browse_comp_cases()

    assert seed_map == {}
    assert len(cases) == 1
    assert cases[0].turns[0].message == "Research question B?"


def test_registry_exposes_browsecomp() -> None:
    """BrowseComp is registered in the framework benchmark registry."""
    from myrm_agent_harness.eval import get_benchmark

    spec = get_benchmark("browsecomp")
    assert spec is not None
    assert spec.id == "browsecomp"
    assert spec.required_tools == ("web_search",)
    assert spec.supports_memory_ab is True


def _run(coro):
    """Run an async BrowseComp operation synchronously (test helper)."""
    import asyncio

    return asyncio.run(coro)
