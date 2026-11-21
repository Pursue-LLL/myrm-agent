"""How share-link buttons fail: a link that cannot be built is dropped (with a WARNING) and the reply is unaffected."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types.components import ActionButton, ComponentRow

# Imported at module level: `deliverable.scanner` binds `channel_t` when first imported, so a first import
# inside a test that patches `app.channels.i18n.channel_t` would leave the mock bound for the whole process.
from app.core.channel_bridge.agent_executor.deliverable.deep_links import build_artifact_deep_links
from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)
from app.services.artifacts.share.share_create import CreatedArtifactShare

_WORKSPACE = "/tmp/chat-workspace"


def _buttons(rows: tuple[ComponentRow, ...]) -> list[ActionButton]:
    """The buttons of the returned rows."""
    return [component for row in rows for component in row if isinstance(component, ActionButton)]


class TestBuildArtifactDeepLinksDegradation:
    """Tests for build_artifact_deep_links when a link cannot be built."""

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
    async def test_empty_shareable_returns_empty(self) -> None:
        acc = StreamAccumulator()
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert rows == ()

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
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-no-ingress", "report.html", "html"),
        )

        with caplog.at_level(logging.WARNING):
            rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert rows == ()
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
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-no-version", "report.html", "html"),
        )

        with caplog.at_level(logging.WARNING):
            rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert rows == ()
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
        acc = StreamAccumulator()
        acc.shareable_artifacts.extend(
            [
                ShareableArtifact("art-partial", "report.html", "html"),
                ShareableArtifact("art-missing", "other.pdf", "pdf"),
            ]
        )

        with caplog.at_level(logging.WARNING):
            rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert len(rows) == 1
        assert any("no version_id in DB" in record.message and "art-missing" in record.message for record in caplog.records)

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
    ) -> None:
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.html", "text/html"))
        with caplog.at_level(logging.WARNING):
            rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert [b.url for b in _buttons(rows)] == ["https://app.example.com/api/v1/public/artifact-share/tok-2"]
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
    @patch("app.database.connection.get_session", side_effect=RuntimeError("database unavailable"))
    async def test_unavailable_database_yields_no_buttons(
        self,
        mock_session: MagicMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Share buttons must never fail the reply they ride on."""
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "html"))
        with caplog.at_level(logging.WARNING):
            rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert rows == ()
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
    ) -> None:
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert rows == ()

    @pytest.mark.asyncio
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no ingress"),
    )
    async def test_no_base_url_safe_degradation(self, mock_ingress: AsyncMock) -> None:
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert rows == ()

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
    ) -> None:
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "text/html"))
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        # Creation failed, so no button is generated.
        assert rows == ()
