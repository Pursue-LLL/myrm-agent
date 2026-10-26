"""Source-sync run: auto-compile waits for the duplicate scan, duplicates are not compiled twice."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.integration.types import IntegrationSyncResult
from myrm_agent_harness.toolkits.wiki import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup import CorpusDedupGovernor, CorpusDedupScanner

from app.services.wiki.source_sync.integration_mirror import mirror_integration_sync_results_to_wiki
from app.services.wiki.source_sync.publish_helpers import publish_source_markdown
from app.services.wiki.source_sync.runner import run_wiki_source_sync
from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig, WikiSourceSyncResult

SAME_BODY = "# Report\n\nThe very same body, pulled from two places."


class Flow:
    """The ordered record of what the run did, shared by every fake the run touches."""

    def __init__(self, structure: WikiStructure) -> None:
        self.structure = structure
        self.events: list[str] = []
        self.compiler = SimpleNamespace(enqueue_file=self._enqueue)

    def _enqueue(self, file_path: Path) -> None:
        self.events.append(f"enqueue:{file_path.name}")

    @property
    def queued(self) -> list[str]:
        return [event.removeprefix("enqueue:") for event in self.events if event.startswith("enqueue:")]


@pytest.fixture
async def flow(tmp_path: Path) -> AsyncIterator[Flow]:
    recorded = Flow(WikiStructure(base_dir=tmp_path))
    archiver = SimpleNamespace(_structure=recorded.structure, _compiler=recorded.compiler)

    async def snapshot(*_: object, **__: object) -> None:
        recorded.events.append("snapshot")

    async def scan(*, agent_id: str | None) -> bool:
        recorded.events.append("scan")
        CorpusDedupScanner(recorded.structure).scan(incremental=True)
        return True

    with (
        patch("app.services.wiki.source_sync.runner.get_session") as session_ctx,
        patch("app.services.wiki.source_sync.state_store.save_wiki_source_sync_state", new=AsyncMock()),
        patch("app.services.wiki.source_sync.runner.resolve_wiki_vault_path", return_value="/tmp/wiki"),
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=archiver),
        patch("app.services.wiki.ingest_events.publish_wiki_ingest_snapshot", new=snapshot),
        patch("app.services.wiki.source_sync.runner.run_post_sync_dedup_scan", new=scan),
    ):
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        yield recorded


def _rss_publishing(bodies: dict[str, str], *, then_crash: bool = False) -> Callable[..., Awaitable[WikiSourceSyncResult]]:
    async def sync_rss(
        structure: WikiStructure,
        *,
        auto_compile: bool,
        compiler_enqueue: object | None,
        **_: object,
    ) -> WikiSourceSyncResult:
        result = WikiSourceSyncResult(source="rss")
        for relative_path, body in bodies.items():
            publish = await publish_source_markdown(
                structure,
                relative_path=relative_path,
                content=body,
                auto_compile=auto_compile,
                compiler_enqueue=compiler_enqueue,
            )
            result.published += int(publish.written)
        if then_crash:
            raise RuntimeError("feed parser crashed")
        return result

    return sync_rss


def _config(**overrides: object) -> WikiSourceSyncConfig:
    return WikiSourceSyncConfig(rss_feeds=["https://example.test/feed"], **overrides)


async def test_duplicates_are_not_compiled_and_the_rest_is_queued_after_the_scan(flow: Flow) -> None:
    bodies = {"rss/a.md": SAME_BODY, "rss/a-copy.md": SAME_BODY, "rss/unique.md": "# Unique\n\nNothing alike."}

    with patch("app.services.wiki.source_sync.runner.sync_rss_feeds_to_wiki", new=_rss_publishing(bodies)):
        run = await run_wiki_source_sync(llm=MagicMock(), config=_config())

    assert run.total_published == 3
    assert flow.queued == ["unique.md"]
    assert flow.events == ["scan", "enqueue:unique.md", "snapshot"]


async def test_a_crashing_connector_still_hands_over_what_it_already_published(flow: Flow) -> None:
    bodies = {"rss/a.md": "# A\n\nfirst", "rss/b.md": "# B\n\nsecond"}
    crashing = _rss_publishing(bodies, then_crash=True)

    with (
        patch("app.services.wiki.source_sync.runner.sync_rss_feeds_to_wiki", new=crashing),
        pytest.raises(RuntimeError, match="feed parser crashed"),
    ):
        await run_wiki_source_sync(llm=MagicMock(), config=_config())

    assert flow.queued == ["a.md", "b.md"]


async def test_a_scan_that_did_not_complete_does_not_cost_the_documents_their_compile(flow: Flow) -> None:
    """Groups stored by an earlier scan say nothing reliable about files published since, so none are held back."""
    for relative_path in ("rss/old-a.md", "rss/old-b.md"):
        earlier = flow.structure.get_raw_file_path(relative_path)
        earlier.parent.mkdir(parents=True, exist_ok=True)
        earlier.write_text(SAME_BODY, encoding="utf-8")
    CorpusDedupScanner(flow.structure).scan(incremental=False)
    bodies = {"rss/a.md": SAME_BODY, "rss/a-copy.md": SAME_BODY}

    async def incomplete_scan(*, agent_id: str | None) -> bool:
        return False

    with (
        patch("app.services.wiki.source_sync.runner.sync_rss_feeds_to_wiki", new=_rss_publishing(bodies)),
        patch("app.services.wiki.source_sync.runner.run_post_sync_dedup_scan", new=incomplete_scan),
    ):
        await run_wiki_source_sync(llm=MagicMock(), config=_config())

    assert flow.queued == ["a.md", "a-copy.md"]


async def test_a_run_that_published_nothing_still_scans_for_files_an_earlier_run_left_held(flow: Flow) -> None:
    leftover = flow.structure.get_raw_file_path("rss/leftover.md")
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("# Leftover\n\nHeld by a run that died.", encoding="utf-8")
    CorpusDedupGovernor(flow.structure).hold_for_compile(["rss/leftover.md"])

    with patch("app.services.wiki.source_sync.runner.sync_rss_feeds_to_wiki", new=_rss_publishing({})):
        run = await run_wiki_source_sync(llm=MagicMock(), config=_config())

    assert run.total_published == 0
    assert flow.events == ["scan", "enqueue:leftover.md"]


async def test_a_run_that_published_nothing_releases_files_an_earlier_scan_already_covered(flow: Flow) -> None:
    """A hold whose queueing failed, or whose run died after the scan, must not wait for the next new document."""
    leftover = flow.structure.get_raw_file_path("rss/leftover.md")
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_text("# Leftover\n\nScanned, then the run died.", encoding="utf-8")
    CorpusDedupGovernor(flow.structure).hold_for_compile(["rss/leftover.md"])
    CorpusDedupScanner(flow.structure).scan(incremental=False)

    with patch("app.services.wiki.source_sync.runner.sync_rss_feeds_to_wiki", new=_rss_publishing({})):
        await run_wiki_source_sync(llm=MagicMock(), config=_config())

    assert flow.events == ["enqueue:leftover.md"]


async def test_nothing_is_deferred_or_queued_when_auto_compile_is_off(flow: Flow) -> None:
    seen: dict[str, object] = {}
    inner = _rss_publishing({"rss/a.md": "# A\n\nfirst"})

    async def spy(structure: WikiStructure, **kwargs: object) -> WikiSourceSyncResult:
        seen["compiler_enqueue"] = kwargs["compiler_enqueue"]
        return await inner(structure, **kwargs)

    with patch("app.services.wiki.source_sync.runner.sync_rss_feeds_to_wiki", new=spy):
        await run_wiki_source_sync(llm=MagicMock(), config=_config(auto_compile=False))

    assert seen["compiler_enqueue"] is None
    assert flow.queued == []


async def test_mirrored_integration_items_go_through_the_enqueuer_they_are_given(flow: Flow) -> None:
    result = IntegrationSyncResult(
        tree_id="t1",
        provider="mcp:notion",
        new_items=[{"title": "Roadmap", "text": "Ship it", "external_id": "page-1"}],
    )
    held: list[Path] = []

    summary = await mirror_integration_sync_results_to_wiki(
        [result],
        llm=MagicMock(),
        agent_id=None,
        auto_compile=True,
        compiler_enqueue=SimpleNamespace(enqueue_file=held.append),
    )

    assert summary.published == 1
    assert [path.name for path in held] == ["page-1.md"]
    assert flow.queued == []
