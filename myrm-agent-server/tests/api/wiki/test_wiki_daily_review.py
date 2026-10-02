"""Daily review ingest + standard template seed + compounding cron tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

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


async def test_daily_review_compound_job_silent_without_window_review(client: TestClient) -> None:
    from app.services.wiki.daily_review import run_wiki_daily_review_compound_job

    # Isolate an empty vault so the [SILENT] path is deterministic.
    with patch(
        "app.services.wiki.vault.resolve_wiki_vault_path",
        return_value=Path(tempfile.mkdtemp(prefix="daily_review_silent_")) / "wiki",
    ):
        result = await run_wiki_daily_review_compound_job(llm=None)
    assert result.recent_review_files == 0
    assert result.summary_text == "[SILENT]"


async def test_daily_review_compound_job_summarizes_recent_ingest(client: TestClient) -> None:
    from app.services.wiki.daily_review import run_wiki_daily_review_compound_job

    response = client.post(
        "/api/v1/wiki/daily-review",
        json={"text": "复盘：完成 daily review ingest 集成测试。", "title": "compound-test"},
    )
    assert response.status_code == 200, response.text

    result = await run_wiki_daily_review_compound_job(llm=None)
    assert result.recent_review_files >= 1
    assert result.summary_text != "[SILENT]"
    assert "Daily review compounding" in result.summary_text


async def test_daily_review_compound_job_llm_summary_links_pending_panel() -> None:
    """The compiled-summary branch reports real window output and links the panel."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from app.services.wiki.daily_review import DAILY_REVIEW_RAW_DIR, run_wiki_daily_review_compound_job
    from app.services.wiki.vault import reset_wiki_archiver_cache_for_tests

    vault_root = Path(tempfile.mkdtemp(prefix="daily_review_llm_")) / "wiki"
    reset_wiki_archiver_cache_for_tests()
    try:
        with patch("app.services.wiki.vault.service.resolve_wiki_vault_path", return_value=vault_root):
            review_dir = vault_root / "raw" / DAILY_REVIEW_RAW_DIR
            review_dir.mkdir(parents=True, exist_ok=True)
            (review_dir / "llm-branch-review.md").write_text(
                "---\nsource: daily-review\n---\nprogress notes", encoding="utf-8"
            )
            result = await run_wiki_daily_review_compound_job(llm=FakeListChatModel(responses=[]))
    finally:
        reset_wiki_archiver_cache_for_tests()

    assert result.recent_review_files == 1
    assert result.window_drafts == 0
    assert "0 draft(s) produced (none)" in result.summary_text
    assert "wikiTab=pendingEdits" in result.summary_text


async def test_daily_review_compound_job_covers_overnight_writer(client: TestClient) -> None:
    """A review written after the previous cron run must not be silently dropped."""
    import os
    import time

    from app.services.wiki.daily_review import DAILY_REVIEW_RAW_DIR, run_wiki_daily_review_compound_job

    vault_root = Path(tempfile.mkdtemp(prefix="daily_review_overnight_")) / "wiki"
    with patch("app.services.wiki.vault.resolve_wiki_vault_path", return_value=vault_root):
        review_dir = vault_root / "raw" / DAILY_REVIEW_RAW_DIR
        review_dir.mkdir(parents=True, exist_ok=True)
        yesterday = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 26 * 3600))
        overnight = review_dir / f"{yesterday}_late-night.md"
        overnight.write_text("---\nsource: daily-review\n---\nlate night reflections", encoding="utf-8")
        # Written after the previous 21:30 cron run: 23h ago stays inside the 24h window.
        stale_time = time.time() - 23 * 3600
        os.utime(overnight, (stale_time, stale_time))
        too_old = review_dir / "2020-01-01_ancient.md"
        too_old.write_text("---\nsource: daily-review\n---\nancient reflections", encoding="utf-8")
        os.utime(too_old, (time.time() - 30 * 3600, time.time() - 30 * 3600))

        result = await run_wiki_daily_review_compound_job(llm=None)

    assert result.recent_review_files == 1
    assert result.summary_text != "[SILENT]"
    assert "1 journal(s)" in result.summary_text


async def test_window_draft_stats_are_status_agnostic_and_deduped() -> None:
    """Window numbers reflect real output: reviewed drafts stay counted, recompiles deduped."""
    from myrm_agent_harness.toolkits.wiki.pipeline.pending import WikiPendingEditsManager

    from app.services.wiki.daily_review.runner import _window_draft_stats

    class _FakeArchiver:
        def __init__(self, mgr: WikiPendingEditsManager) -> None:
            self._pending_mgr = mgr

    structure = WikiStructure(tempfile.mkdtemp(prefix="daily_review_stats_"))
    structure.ensure_structure()
    mgr = WikiPendingEditsManager(structure)
    reviewed_id = mgr.add_pending_edit("Knowledge/ReviewedByUser", "draft v1")
    mgr.add_pending_edit("Methods/StillPending", "draft")
    mgr.add_pending_edit("Go 语言笔记", "root-level concept outside the four dimensions")
    mgr.reject_edit(reviewed_id)
    # Recompiling the same concept replaces the old draft; it must count once.
    mgr.add_pending_edit("Knowledge/ReviewedByUser", "draft v2")

    counts, other_drafts, total_drafts = _window_draft_stats(
        _FakeArchiver(mgr), "2000-01-01 00:00:00"
    )

    assert counts == {"Projects": 0, "Knowledge": 1, "Methods": 1, "Comparisons": 0}
    assert other_drafts == 1
    assert total_drafts == 3  # exact pending box size, uncapped by LIMIT 50


async def test_archiver_compiler_uses_four_dimension_prompt() -> None:
    from app.services.wiki.daily_review import FOUR_DIMENSION_EXTRACT_PROMPT
    from app.services.wiki.vault import get_wiki_archiver

    archiver = get_wiki_archiver(None, agent_id="default")
    assert (
        archiver._compiler._compile_config.extract_concepts_prompt_template
        == FOUR_DIMENSION_EXTRACT_PROMPT
    )
