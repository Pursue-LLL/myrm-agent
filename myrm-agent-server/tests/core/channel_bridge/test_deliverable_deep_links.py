"""Unit tests for the share-link buttons ChannelAgentExecutor adds to artifact deliveries."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)


class TestBuildArtifactDeepLinks:
    """Tests for build_artifact_deep_links URL generation."""

    @pytest.mark.asyncio
    async def test_empty_shareable_returns_empty(self):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        buttons = await build_artifact_deep_links(acc, "en")
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
            buttons = await build_artifact_deep_links(acc, "en")

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
            buttons = await build_artifact_deep_links(acc, "en")

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
        "app.services.artifacts.share.share_token.create_artifact_share_token",
        return_value=("token-abc", 9999999999),
    )
    async def test_missing_version_id_logs_warning(
        self,
        mock_token: MagicMock,
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
            buttons = await build_artifact_deep_links(acc, "en")

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
        "app.services.artifacts.share.share_token.create_artifact_share_token",
        return_value=("tok-abc123", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        return_value="View interactive page",
    )
    async def test_artifact_without_version_skipped(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
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
        buttons = await build_artifact_deep_links(acc, "en")
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
        "app.services.artifacts.share.share_token.create_artifact_share_token",
        return_value=("tok-abc123", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        return_value="View interactive page",
    )
    async def test_single_artifact_uses_default_label(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
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
        buttons = await build_artifact_deep_links(acc, "en")
        assert len(buttons) == 1
        # Non-named label path → channel_t called without filename kwarg.
        call_kwargs = mock_t.call_args.kwargs
        assert "filename" not in call_kwargs

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
        "app.services.artifacts.share.share_token.create_artifact_share_token",
        side_effect=RuntimeError("token service down"),
    )
    @patch(
        "app.channels.i18n.channel_t",
        return_value="View interactive page",
    )
    async def test_share_token_failure_skipped_gracefully(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        """A share-token failure drops that button but keeps others alive."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        buttons = await build_artifact_deep_links(acc, "en")
        assert buttons == ()

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
        buttons = await build_artifact_deep_links(acc, "en")
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
        buttons = await build_artifact_deep_links(acc, "en")
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
        "app.services.artifacts.share.share_token.create_artifact_share_token",
        return_value=("tok-multi", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        side_effect=lambda _l, _k, **kw: kw.get("filename", "view"),
    )
    async def test_multi_artifact_uses_named_label(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.pdf", "application/pdf"))
        buttons = await build_artifact_deep_links(acc, "zh")
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
        "app.services.artifacts.share.share_token.create_artifact_share_token",
        side_effect=RuntimeError("HMAC key missing"),
    )
    @patch("app.channels.i18n.channel_t", return_value="view")
    async def test_token_generation_failure_skips_button(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "text/html"))
        buttons = await build_artifact_deep_links(acc, "en")
        # Token failed, so no button is generated.
        assert buttons == ()
