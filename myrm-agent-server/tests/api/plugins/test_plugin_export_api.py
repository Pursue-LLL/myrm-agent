"""Agent Plugins expert export API tests (HTTP contract layer).

Covers /export/preview (cards, omitted list, redaction findings, dry-run size) and
/export (ZIP response, review decisions, error mapping) on an isolated FastAPI app
that mounts only the plugin export router.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from typing import cast
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from myrm_agent_harness.agent.plugins import PluginPackageResult

from app.api.plugins import export as export_module
from tests.support.export_world import SKILL_MD, ExportWorld

PRESET_ONLY = "web-research"
PROMPT_PATH = "experts/1-Lead/system_prompt.md"
TOKEN = "ghp_ApiCanary0123456789abcdef"


@pytest.fixture
def client() -> TestClient:
    app = FastAPI(title="Plugin Export Test App")
    app.include_router(export_module.router, prefix="/api/v1/plugins")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def world() -> Iterator[ExportWorld]:
    with ExportWorld().installed() as installation:
        yield installation


@pytest.fixture
def team(world: ExportWorld) -> ExportWorld:
    """An expert with a custom skill, a preset skill, one shareable and one local connector, and a sub-expert."""
    world.custom_skill("local::a1", "notes", {"SKILL.md": SKILL_MD}, directory="notes", source="clawhub")
    world.preset_skill(PRESET_ONLY, PRESET_ONLY)
    world.server(
        name="docs",
        type="streamable_http",
        url="https://docs.example.com/mcp",
        headers={"Authorization": "Bearer live"},
    )
    world.server(name="local-db", type="stdio", command="/opt/db/server")
    world.expert(
        "lead",
        "Lead",
        skills=("local::a1", PRESET_ONLY),
        mcps=("docs", "local-db"),
        subagents=("worker",),
        model="gpt-4o",
        system_prompt=f"Use {TOKEN} for the API.",
    )
    world.expert("worker", "Worker")
    return world


def _detail(response: Response) -> dict[str, str]:
    return cast("dict[str, str]", response.json()["detail"])


def _package_text(package: bytes) -> str:
    """Names and decompressed contents of every entry, as one searchable text."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        return "\n".join(name + "\n" + archive.read(name).decode("utf-8", "replace") for name in archive.namelist())


class TestPreview:
    def test_describes_everything_the_package_would_contain(self, client: TestClient, team: ExportWorld) -> None:
        body = client.post("/api/v1/plugins/export/preview", json={"agent_id": "lead"}).json()

        assert (body["plugin_name"], body["version"]) == ("lead", "1.0.0")
        lead, worker = body["experts"]
        assert (lead["name"], lead["is_entry"], lead["subagent_names"]) == ("Lead", True, ["Worker"])
        assert lead["connector_names"] == ["docs"]
        assert lead["recommended_model"] == "gpt-4o"
        assert (worker["name"], worker["is_entry"]) == ("Worker", False)
        assert body["skills"] == [
            {"name": "notes", "source": "custom", "file_count": 1, "version": "1.0.0", "origin": "clawhub"},
            {"name": PRESET_ONLY, "source": "preset", "file_count": 0, "version": None, "origin": None},
        ]
        assert body["connectors"] == [{"name": "docs", "type": "streamable_http", "secret_keys": ["Authorization"]}]
        assert body["package_bytes"] > 0
        assert body["build_error"] is None

    def test_lists_what_is_left_out_with_a_code_the_ui_can_localize(self, client: TestClient, team: ExportWorld) -> None:
        body = client.post("/api/v1/plugins/export/preview", json={"agent_id": "lead"}).json()

        assert body["omitted"] == [
            {"kind": "connector", "name": "local-db", "reason": "local_path", "owner": "Lead"},
        ]

    def test_findings_are_returned_with_the_diff_and_a_digest_for_the_decision(
        self, client: TestClient, team: ExportWorld
    ) -> None:
        body = client.post("/api/v1/plugins/export/preview", json={"agent_id": "lead"}).json()

        assert body["is_safe"] is False
        assert body["review_digest"]
        (finding,) = body["redactions"][PROMPT_PATH]
        assert TOKEN in finding["original"]
        assert TOKEN not in finding["redacted"]
        assert set(finding) == {"line_number", "original", "redacted", "kinds"}
        assert finding["kinds"] == ["api_token"]

    def test_a_clean_expert_has_no_findings(self, client: TestClient, world: ExportWorld) -> None:
        world.expert("lead", "Lead")

        body = client.post("/api/v1/plugins/export/preview", json={"agent_id": "lead"}).json()

        assert body["is_safe"] is True
        assert body["redactions"] is None

    @pytest.mark.parametrize(
        ("agent_id", "status", "code"),
        [("missing", 404, "expert_not_found"), ("general", 422, "built_in_expert")],
    )
    def test_refusals_carry_a_machine_readable_code(
        self, client: TestClient, world: ExportWorld, agent_id: str, status: int, code: str
    ) -> None:
        world.expert("general", "General", built_in=True)

        response = client.post("/api/v1/plugins/export/preview", json={"agent_id": agent_id})

        assert response.status_code == status
        assert _detail(response)["error_code"] == code
        assert _detail(response)["message"]

    def test_an_empty_expert_id_is_rejected_before_any_work(self, client: TestClient, world: ExportWorld) -> None:
        assert client.post("/api/v1/plugins/export/preview", json={"agent_id": ""}).status_code == 422


class TestExport:
    def test_returns_the_verified_package_as_a_download(self, client: TestClient, team: ExportWorld) -> None:
        response = client.post("/api/v1/plugins/export", json={"agent_id": "lead", "apply_redactions": True})

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["content-disposition"] == 'attachment; filename="lead_v1.0.0.zip"'
        text = _package_text(response.content)
        assert "skills/notes/SKILL.md" in text
        assert TOKEN not in text

    def test_unreviewed_findings_block_the_download(self, client: TestClient, team: ExportWorld) -> None:
        response = client.post("/api/v1/plugins/export", json={"agent_id": "lead"})

        assert response.status_code == 409
        assert _detail(response)["error_code"] == "redaction_review_required"

    def test_kept_findings_need_the_digest_of_the_reviewed_preview(self, client: TestClient, team: ExportWorld) -> None:
        keep = {"agent_id": "lead", "ignored_redactions": {PROMPT_PATH: [0]}}

        stale = client.post("/api/v1/plugins/export", json={**keep, "review_digest": "0" * 64})
        fresh = client.post("/api/v1/plugins/export/preview", json={"agent_id": "lead"}).json()["review_digest"]
        kept = client.post("/api/v1/plugins/export", json={**keep, "review_digest": fresh})

        assert (stale.status_code, _detail(stale)["error_code"]) == (409, "export_changed_since_preview")
        assert kept.status_code == 200
        assert TOKEN in _package_text(kept.content)

    def test_a_package_that_fails_verification_is_not_handed_out(self, client: TestClient, team: ExportWorld) -> None:
        failure = PluginPackageResult(success=False, zip_content=None, filename=None, error="verification failed")
        with patch("app.services.plugins.export_service.build_plugin_bundle", return_value=failure):
            response = client.post("/api/v1/plugins/export", json={"agent_id": "lead", "apply_redactions": True})

        assert response.status_code == 422
        assert _detail(response) == {"message": "verification failed", "error_code": "package_rejected"}

    def test_unknown_expert(self, client: TestClient, world: ExportWorld) -> None:
        response = client.post("/api/v1/plugins/export", json={"agent_id": "missing"})

        assert (response.status_code, _detail(response)["error_code"]) == (404, "expert_not_found")
