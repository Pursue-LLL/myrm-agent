"""Unit tests for the share-link buttons ChannelAgentExecutor adds to artifact deliveries."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)
from app.services.artifacts.share.share_create import CreatedArtifactShare

_WORKSPACE = "/tmp/chat-workspace"


class TestBuildArtifactDeepLinks:
    """Tests for build_artifact_deep_links URL generation."""

    @pytest.fixture(autouse=True)
    def _share_db_session(self) -> Iterator[MagicMock]:
        """Share creation is mocked per test, so the session it would receive is a stand-in."""
        session = MagicMock()

        @asynccontextmanager
        async def _get_session() -> AsyncIterator[MagicMock]:
            yield session

        with patch("app.database.connection.get_session", new=_get_session):
            yield session

    @pytest.mark.asyncio
    async def test_empty_shareable_returns_empty(self):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert buttons == ()

    @pytest.mark.asyncio
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="",
    )
    async def test_missing_ingress_logs_warning(
        self,
        mock_base: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-no-ingress", "report.html", "html"),
        )

        with caplog.at_level(logging.WARNING):
            buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert buttons == ()
        assert any("no public ingress base URL" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    async def test_empty_version_map_logs_warning(
        self,
        mock_base: AsyncMock,
        mock_fetch: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-no-version", "report.html", "html"),
        )

        with caplog.at_level(logging.WARNING):
            buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert buttons == ()
        assert any("no artifact versions found" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-partial": "ver-partial"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("token-abc", 9999999999),
    )
    async def test_missing_version_id_logs_warning(
        self,
        mock_token: AsyncMock,
        mock_base: AsyncMock,
        mock_fetch: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.extend(
            [
                ShareableArtifact("art-partial", "report.html", "html"),
                ShareableArtifact("art-missing", "other.pdf", "pdf"),
            ]
        )

        with caplog.at_level(logging.WARNING):
            buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert len(buttons) == 1
        assert any("no version_id in DB" in record.message and "art-missing" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("tok-abc123", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        return_value="View interactive page",
    )
    async def test_artifact_without_version_skipped(
        self,
        mock_t: MagicMock,
        mock_token: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        """Artifacts absent from the version map get no button; others still do."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        acc.shareable_artifacts.append(
            ShareableArtifact("art-missing", "gone.html", "text/html"),
        )
        buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert len(buttons) == 1
        btn = buttons[0]
        assert btn.url == "https://app.example.com/api/v1/public/artifact-share/tok-abc123"
        assert btn.label == "View interactive page"

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("tok-abc123", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        return_value="View interactive page",
    )
    async def test_single_artifact_uses_default_label(
        self,
        mock_t: MagicMock,
        mock_token: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        """A single artifact uses the non-named deep-link label (else branch)."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert len(buttons) == 1
        # Non-named label path → channel_t called without filename kwarg.
        call_kwargs = mock_t.call_args.kwargs
        assert "filename" not in call_kwargs

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001", "art-002": "ver-002"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("bundle missing"), CreatedArtifactShare("tok-2", 604800)],
    )
    @patch("app.channels.i18n.channel_t", return_value="View interactive page")
    async def test_share_creation_failure_drops_only_that_button(
        self,
        mock_t: MagicMock,
        mock_create: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.html", "text/html"))
        with caplog.at_level(logging.WARNING):
            buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert [b.url for b in buttons] == ["https://app.example.com/api/v1/public/artifact-share/tok-2"]
        assert any("Failed to create share link for artifact art-001" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("tok-1", 604800),
    )
    @patch("app.channels.i18n.channel_t", return_value="View interactive page")
    async def test_link_is_created_through_the_registered_share_service(
        self,
        mock_t: MagicMock,
        mock_create: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
        _share_db_session: MagicMock,
    ):
        """The link is signed, snapshotted and registered by the same service as the share dialog."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "html"))
        await build_artifact_deep_links(acc, "en", _WORKSPACE)

        mock_create.assert_awaited_once_with(
            _share_db_session,
            _WORKSPACE,
            artifact_id="art-001",
            version_id="ver-001",
            artifact_type="html",
        )

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("tok-1", 604800),
    )
    @patch("app.platform_utils.workspace_root.get_workspace_root", return_value="/run/root")
    @patch("app.channels.i18n.channel_t", return_value="View interactive page")
    async def test_chat_without_workspace_falls_back_to_the_run_root(
        self,
        mock_t: MagicMock,
        mock_root: MagicMock,
        mock_create: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "html"))
        await build_artifact_deep_links(acc, "en", None)

        assert mock_create.await_args.args[1] == "/run/root"

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch("app.database.connection.get_session", side_effect=RuntimeError("database unavailable"))
    async def test_unavailable_database_yields_no_buttons(
        self,
        mock_session: MagicMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """Share buttons must never fail the reply they ride on."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "html"))
        with caplog.at_level(logging.WARNING):
            buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert buttons == ()
        assert any("Failed to create artifact share links" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    async def test_no_version_returns_empty(
        self,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert buttons == ()

    @pytest.mark.asyncio
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no ingress"),
    )
    async def test_no_base_url_safe_degradation(self, mock_ingress: AsyncMock):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert buttons == ()

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001", "art-002": "ver-002"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("tok-multi", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        side_effect=lambda _l, _k, **kw: kw.get("filename", "view"),
    )
    async def test_multi_artifact_uses_named_label(
        self,
        mock_t: MagicMock,
        mock_token: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.pdf", "application/pdf"))
        buttons = await build_artifact_deep_links(acc, "zh", _WORKSPACE)
        assert len(buttons) == 2
        # channel_t called with artifact_deep_link_named for multi
        assert mock_t.call_args_list[0].args[1] == "artifact_deep_link_named"

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        side_effect=RuntimeError("HMAC key missing"),
    )
    @patch("app.channels.i18n.channel_t", return_value="view")
    async def test_share_creation_failure_skips_button(
        self,
        mock_t: MagicMock,
        mock_token: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "text/html"))
        buttons = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        # Creation failed, so no button is generated.
        assert buttons == ()
