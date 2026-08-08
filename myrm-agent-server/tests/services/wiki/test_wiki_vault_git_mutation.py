"""Integration tests for wiki vault git snapshots on REST mutations."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.portability.vault_git import maybe_commit_vault_git_snapshot

from app.services.wiki.vault import after_wiki_vault_mutation

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


class _ArchiverStub:
    def __init__(self, structure: WikiStructure, config: WikiConfig) -> None:
        self._structure = structure
        self._config = config

    def commit_vault_git(self, reason: str):
        return maybe_commit_vault_git_snapshot(self._structure, self._config, reason=reason)


@pytest.mark.asyncio
async def test_after_wiki_vault_mutation_commits_apply_changes(tmp_path) -> None:
    structure = WikiStructure(tmp_path / "vault")
    structure.ensure_structure()
    concept_path = structure.get_concept_file_path("Physics/Gravity")
    concept_path.write_text("---\ntype: concept\n---\n\n# Gravity\n", encoding="utf-8")

    archiver = _ArchiverStub(structure, WikiConfig(enable_version_control=True))
    await after_wiki_vault_mutation(archiver, "apply mutation")  # type: ignore[arg-type]

    git_dir = structure.base_dir / ".git"
    assert git_dir.is_dir()
    log = subprocess.run(
        ["git", "-C", str(structure.base_dir), "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip() == "myrm: apply mutation"


def test_apply_endpoint_triggers_vault_mutation_hook() -> None:
    from fastapi.testclient import TestClient
    from myrm_agent_harness.toolkits.wiki.pipeline.apply.types import WikiApplyOp, WikiApplyResult

    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    client = TestClient(app)
    apply_result = WikiApplyResult(
        success=True,
        op=WikiApplyOp.PATCH_COMPILED_TRUTH,
        concept_name="Gravity",
        message="ok",
        content_hash="abc",
    )
    with patch(
        "app.api.wiki.router._after_wiki_vault_mutation",
        new_callable=AsyncMock,
    ) as mutation_mock, patch(
        "myrm_agent_harness.toolkits.wiki.pipeline.apply.apply_wiki_mutation",
        new_callable=AsyncMock,
        return_value=apply_result,
    ), patch(
        "app.middleware.auth.resolve_identity",
        return_value=MagicMock(user_id="local", auth_source="loopback", loopback=True, client_ip="127.0.0.1", private_net=False),
    ):
        response = client.post(
            "/api/v1/wiki/apply",
            json={
                "op": "patch_compiled_truth",
                "concept_name": "Gravity",
                "compiled_truth": "Updated truth.",
            },
        )

    assert response.status_code == 200
    mutation_mock.assert_awaited_once()
    assert mutation_mock.await_args.args[1] == "apply mutation"
