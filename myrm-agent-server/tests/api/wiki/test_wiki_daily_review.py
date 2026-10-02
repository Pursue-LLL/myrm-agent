"""Daily review ingest + standard template seed + compounding cron tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.wiki.core.frontmatter_contract import (
    assert_valid_wiki_frontmatter,
)
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from tests.api.wiki.test_wiki_api import _FakeIdentity

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _bypass_auth() -> None:
    from unittest.mock import patch

    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    from tests.support.minimal_app import build_minimal_app

    return TestClient(build_minimal_app(preset="wiki"))


def _vault_structure() -> WikiStructure:
    from app.services.wiki.vault import resolve_wiki_vault_path

    return WikiStructure(resolve_wiki_vault_path(None))


async def test_daily_review_ingest_is_verbatim_and_idempotent(client: TestClient) -> None:
    body = {
        "text": "今日完成 wiki publish gate 门禁接线；教训：fail-closed 优先于白名单。",
        "title": "gate-wiring",
    }
    first = client.post("/api/v1/wiki/daily-review", json=body)
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["success"] is True
    assert payload["enqueued"] is True
    assert payload["skipped"] is False
    assert payload["raw_path"].startswith("DailyReview/")

    structure = _vault_structure()
    raw_path = structure.raw_dir / payload["raw_path"]
    assert raw_path.exists()
    content = raw_path.read_text(encoding="utf-8")
    assert body["text"] in content, "Review text must be stored verbatim"
    assert 'source: "daily-review"' in content

    # Same-day retry with the same title stays idempotent (skip, no duplicate file).
    second = client.post("/api/v1/wiki/daily-review", json=body)
    assert second.status_code == 200, second.text
    assert second.json()["skipped"] is True
    assert second.json()["enqueued"] is False


async def test_daily_review_rejects_empty_text(client: TestClient) -> None:
    response = client.post("/api/v1/wiki/daily-review", json={"text": ""})
    assert response.status_code == 422, response.text


async def test_standard_templates_seed_is_idempotent_and_force_reseeds(client: TestClient) -> None:
    first = client.post("/api/v1/wiki/templates/seed", json={})
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["success"] is True
    assert set(payload["seeded"]) == set(payload["templates"])
    assert len(payload["templates"]) == 4

    structure = _vault_structure()
    for name in payload["templates"]:
        template_path = structure.templates_dir / f"{name}.md"
        assert template_path.exists(), f"Missing template file: {template_path}"
        assert_valid_wiki_frontmatter(template_path.read_text(encoding="utf-8"))

    # Idempotent: a second plain seed writes nothing.
    second = client.post("/api/v1/wiki/templates/seed", json={})
    assert second.status_code == 200, second.text
    assert second.json()["seeded"] == []

    # Explicit force re-seeds all four templates.
    forced = client.post("/api/v1/wiki/templates/seed", json={"force": True})
    assert forced.status_code == 200, forced.text
    assert set(forced.json()["seeded"]) == set(payload["templates"])


async def test_daily_review_compound_job_silent_without_today_review(client: TestClient) -> None:
    from app.services.wiki.daily_review import run_wiki_daily_review_compound_job

    # Ensure today has no review file: use a fresh isolated structure by checking the real vault.
    result = await run_wiki_daily_review_compound_job(llm=None)
    if result.today_review_files == 0:
        assert result.summary_text == "[SILENT]"
    else:
        # Today already has review files (shared dev vault); summary must be non-silent.
        assert result.summary_text != "[SILENT]"
        assert result.today_review_files > 0


async def test_daily_review_compound_job_summarizes_today_ingest(client: TestClient) -> None:
    from app.services.wiki.daily_review import run_wiki_daily_review_compound_job

    response = client.post(
        "/api/v1/wiki/daily-review",
        json={"text": "复盘：完成 daily review ingest 集成测试。", "title": "compound-test"},
    )
    assert response.status_code == 200, response.text

    result = await run_wiki_daily_review_compound_job(llm=None)
    assert result.today_review_files >= 1
    assert result.summary_text != "[SILENT]"
    assert "今日复盘" in result.summary_text


async def test_archiver_compiler_uses_four_dimension_prompt() -> None:
    from app.services.wiki.daily_review import FOUR_DIMENSION_EXTRACT_PROMPT
    from app.services.wiki.vault import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id="default")
    assert (
        archiver._compiler._compile_config.extract_concepts_prompt_template
        == FOUR_DIMENSION_EXTRACT_PROMPT
    )
