"""Workspace trust API on a folder of hostile files: the real router, the real store, the real database, real files.

[INPUT]
- app.api.security.workspace_trust::router (POS: the FolderGate REST surface under test, mounted without any patch)
- app.services.security.workspace_trust_store (POS: the real registry; a decision is persisted through the test database)
- FIFOs and sparse files in a temp folder (POS: what a repository author can put in a folder the user has not trusted yet)

[OUTPUT]
- Fails when the disclosure of a folder that holds a FIFO as ``SKILL.md`` and sparse multi-megabyte ``mcp.json`` and
  ``.myrm/config.toml`` does not come back with the counts of the honest files, when its hash differs between two previews, or
  when trusting the folder with the hash the user was shown is refused.

[POS]
The folder preview is the first thing a user meets for a folder they have not trusted, and the server builds it on the event
loop. The unit tests of the manifest pin the bounded reads; this file pins that the same folder goes through the whole server
path (request, store, hash, persisted decision) and that the answer is the one an honest reader of the files would give.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security import workspace_trust as workspace_trust_module

BASE = "/api/v1/security/workspace-trust"
SPARSE_BYTES = 64 * 1024 * 1024
ANSWER_WITHIN_SECONDS = 10.0

# A blocked read is a deadlock inside the event loop; the signal-based timeout cannot unwind it and the test client would then
# wait for that thread forever, so the thread method ends the run with a stack dump.
pytestmark = [
    pytest.mark.skipif(sys.platform == "win32", reason="FIFOs and sparse files are POSIX"),
    pytest.mark.timeout(60, method="thread"),
]

_SKILL = "---\nname: {name}\ndescription: A skill the folder really ships.\n---\n\nBody.\n"


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI(title="Workspace Trust Hostile Folder Test App")
    app.include_router(workspace_trust_module.router, prefix=BASE)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def hostile_folder(tmp_path: Path) -> Path:
    """One honest skill, one honest rule file, and the files a hostile repository author would add next to them."""
    root = tmp_path / "hostile"
    (root / ".myrm").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# Rules\nUse tabs.\n", encoding="utf-8")
    honest = root / "skills" / "honest"
    honest.mkdir(parents=True)
    (honest / "SKILL.md").write_text(_SKILL.format(name="honest"), encoding="utf-8")
    hostile = root / "skills" / "hostile"
    hostile.mkdir()
    os.mkfifo(hostile / "SKILL.md")
    for sparse in (root / "mcp.json", root / ".myrm" / "config.toml"):
        with sparse.open("wb") as handle:
            handle.truncate(SPARSE_BYTES)
    return root


def _preview(client: TestClient, folder: Path) -> tuple[dict[str, object], float]:
    started = time.perf_counter()
    response = client.post(f"{BASE}/manifest", json={"path": str(folder)})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    return body["data"], elapsed


def test_a_folder_of_hostile_files_is_disclosed_with_the_counts_of_its_honest_files(
    client: TestClient, hostile_folder: Path
) -> None:
    data, elapsed = _preview(client, hostile_folder)

    assert elapsed < ANSWER_WITHIN_SECONDS
    assert data["skill_count"] == 1
    assert data["rule_count"] == 1
    assert data["mcp_count"] == 1  # a config that cannot be read in full still shows up, as one server
    assert data["has_myrm_config"] is True
    assert data["repo_command_prefixes"] == []
    assert data["requires_trust"] is True
    assert data["current_level"] is None


def test_the_hash_is_stable_and_trusting_with_it_is_accepted_and_persisted(client: TestClient, hostile_folder: Path) -> None:
    first, _ = _preview(client, hostile_folder)
    second, _ = _preview(client, hostile_folder)
    assert first["manifest_hash"] == second["manifest_hash"]

    try:
        decided = client.post(
            f"{BASE}/decide",
            json={"path": str(hostile_folder), "level": "TRUSTED", "manifest_hash": first["manifest_hash"]},
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["data"]["level"] == "TRUSTED"

        listed = client.get(BASE).json()["data"]
        assert [entry["level"] for entry in listed if entry["path"] == first["canonical_path"]] == ["TRUSTED"]
    finally:
        client.delete(BASE, params={"path": str(hostile_folder), "remove": "true"})


def test_a_folder_that_changed_after_the_preview_cannot_be_trusted_with_the_old_hash(
    client: TestClient, hostile_folder: Path
) -> None:
    shown, _ = _preview(client, hostile_folder)
    (hostile_folder / "AGENTS.md").unlink()
    (hostile_folder / "skills" / "honest" / "SKILL.md").unlink()

    refused = client.post(
        f"{BASE}/decide",
        json={"path": str(hostile_folder), "level": "TRUSTED", "manifest_hash": shown["manifest_hash"]},
    )

    assert refused.status_code == 400, refused.text
    assert "out of date" in refused.text
