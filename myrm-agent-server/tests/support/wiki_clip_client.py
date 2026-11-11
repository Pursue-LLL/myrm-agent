"""[INPUT]
- tests.support.minimal_app::build_minimal_app (POS: lightweight FastAPI test app, wiki preset)
- app.api.wiki.router::_get_wiki_archiver (POS: the archiver dependency, overridden with a vault under tmp_path)
- app.services.wiki::MemoryToWikiArchiver (POS: real archiver over the temporary vault)

[OUTPUT]
- bypass_loopback_auth(): context manager that authenticates every request as the local loopback user
- build_wiki_client(tmp_path) / cleanup_wiki_client(client): TestClient on the wiki routes bound to a temporary vault
- poll_clip_job(client, job_id): waits until a clip job has succeeded or failed

[POS]
Shared client, auth bypass and job polling for the wiki clip API tests
(`tests/api/wiki/test_wiki_clip_api.py`, `tests/api/wiki/test_wiki_clip_form_parsing.py`).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.core.security.auth.identity import LOCAL_USER_ID
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from tests.support.minimal_app import build_minimal_app


@dataclass(frozen=True, slots=True)
class _LoopbackIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@contextmanager
def bypass_loopback_auth() -> Iterator[None]:
    with patch("app.middleware.auth.resolve_identity", return_value=_LoopbackIdentity()):
        yield


def build_wiki_client(
    tmp_path: Path,
) -> tuple[TestClient, MemoryToWikiArchiver, WikiStructure]:
    from app.api.wiki.router import _get_wiki_archiver

    archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=str(tmp_path / "wiki"))
    structure = archiver._structure
    structure.ensure_structure()

    app = build_minimal_app(preset="wiki")

    async def _override_archiver() -> MemoryToWikiArchiver:
        return archiver

    app.dependency_overrides[_get_wiki_archiver] = _override_archiver
    patcher = patch(
        "app.services.wiki.vault.get_wiki_structure",
        return_value=structure,
    )
    patcher.start()
    client = TestClient(app)
    client._wiki_archiver_patcher = patcher  # type: ignore[attr-defined]
    return client, archiver, structure


def cleanup_wiki_client(client: TestClient) -> None:
    client.app.dependency_overrides.clear()
    patcher = getattr(client, "_wiki_archiver_patcher", None)
    if patcher is not None:
        patcher.stop()


def poll_clip_job(client: TestClient, job_id: str) -> dict[str, object]:
    final: dict[str, object] | None = None
    for _ in range(40):
        status = client.get(f"/api/v1/wiki/clip/{job_id}")
        assert status.status_code == 200
        final = status.json()
        if final["state"] in {"succeeded", "failed"}:
            return final
        time.sleep(0.05)
    raise AssertionError(f"clip job timed out: {final}")
