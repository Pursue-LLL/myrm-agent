"""Unit tests for the share-link buttons ChannelAgentExecutor adds to artifact deliveries."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.outbound_prepare import downgrade_components
from app.channels.types import OutboundMessage
from app.channels.types.components import ActionButton, ComponentRow
from app.channels.types.status import ChannelCapabilities

# Imported at module level: `deliverable.scanner` binds `channel_t` when first imported, so a first import
# inside a test that patches `app.channels.i18n.channel_t` would leave the mock bound for the whole process.
from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
    MAX_SHARE_BUTTONS,
    build_artifact_deep_links,
)
from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)
from app.services.artifacts.share.share_create import CreatedArtifactShare
from app.services.audit.share_events import ShareSource

_WORKSPACE = "/tmp/chat-workspace"


def _buttons(rows: tuple[ComponentRow, ...]) -> list[ActionButton]:
    """The buttons of the returned rows."""
    return [component for row in rows for component in row if isinstance(component, ActionButton)]


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
    ) -> None:
        """Artifacts absent from the version map get no button; others still do."""
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        acc.shareable_artifacts.append(
            ShareableArtifact("art-missing", "gone.html", "text/html"),
        )
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert len(rows) == 1
        btn = _buttons(rows)[0]
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
    ) -> None:
        """A single artifact uses the non-named deep-link label (else branch)."""
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert len(rows) == 1
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
    ) -> None:
        """The link is signed, snapshotted and registered by the same service as the share dialog."""
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "html"))
        await build_artifact_deep_links(acc, "en", _WORKSPACE)

        mock_create.assert_awaited_once_with(
            _share_db_session,
            _WORKSPACE,
            artifact_id="art-001",
            version_id="ver-001",
            artifact_type="html",
            source=ShareSource.IM,
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
    ) -> None:
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "html"))
        await build_artifact_deep_links(acc, "en", None)

        assert mock_create.await_args_list[-1].args[1] == "/run/root"

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
    ) -> None:
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.pdf", "application/pdf"))
        rows = await build_artifact_deep_links(acc, "zh", _WORKSPACE)
        assert len(rows) == 2
        # channel_t called with artifact_deep_link_named for multi
        assert mock_t.call_args_list[0].args[1] == "artifact_deep_link_named"

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
        side_effect=[CreatedArtifactShare("tok-1", 604800), CreatedArtifactShare("tok-2", 604800)],
    )
    @patch("app.channels.i18n.channel_t", side_effect=lambda _l, _k, **kw: kw.get("filename", "view"))
    async def test_each_link_is_a_row_the_outbound_pipeline_accepts(
        self,
        mock_t: MagicMock,
        mock_create: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ) -> None:
        """A bare button where a row belongs makes outbound preparation raise (a button is not iterable)."""
        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.pdf", "application/pdf"))
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)
        assert [len(row) for row in rows] == [1, 1]

        reply = OutboundMessage(channel="telegram", recipient_id="r", content="done", user_id="u", components=rows)

        native = downgrade_components(reply, ChannelCapabilities(buttons=True), channel_name="telegram")
        assert native.components == rows

        text_only = downgrade_components(reply, ChannelCapabilities(buttons=False), channel_name="telegram")
        assert text_only.components == ()
        assert "artifact-share/tok-1" in text_only.content
        assert "artifact-share/tok-2" in text_only.content

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={f"art-{i}": f"ver-{i}" for i in range(7)},
    )
    @patch(
        "app.core.infra.ingress.resolve_public_link_base",
        new_callable=AsyncMock,
        return_value="https://app.example.com",
    )
    @patch(
        "app.services.artifacts.share.share_create.create_artifact_share",
        new_callable=AsyncMock,
        return_value=CreatedArtifactShare("tok", 604800),
    )
    @patch("app.channels.i18n.channel_t", side_effect=lambda _l, _k, **kw: kw.get("filename", "view"))
    async def test_only_the_first_artifacts_get_a_share_button(
        self,
        mock_t: MagicMock,
        mock_create: AsyncMock,
        mock_base: AsyncMock,
        mock_versions: AsyncMock,
    ) -> None:
        """Only the first MAX_SHARE_BUTTONS artifacts get a share link made; the others still go out as attachments."""
        acc = StreamAccumulator()
        for i in range(7):
            acc.shareable_artifacts.append(ShareableArtifact(f"art-{i}", f"page-{i}.html", "text/html"))
        rows = await build_artifact_deep_links(acc, "en", _WORKSPACE)

        assert len(rows) == MAX_SHARE_BUTTONS == 5
        assert mock_create.await_count == MAX_SHARE_BUTTONS
        assert mock_versions.await_args_list[-1].args[0] == [f"art-{i}" for i in range(MAX_SHARE_BUTTONS)]
        assert [button.action_id for button in _buttons(rows)] == [f"artifact:share:art-{i}" for i in range(MAX_SHARE_BUTTONS)]
