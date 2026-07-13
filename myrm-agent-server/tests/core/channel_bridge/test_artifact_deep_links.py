"""Unit tests for artifact deep link injection in ChannelAgentExecutor.

Tests _collect_channel_artifacts shareable artifact tracking,
_build_artifact_deep_links URL generation + redundant attachment removal,
and _fetch_artifact_versions DB batch lookup.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import MediaAttachment, MediaType
from app.core.channel_bridge.executor_helpers import ShareableArtifact, StreamAccumulator


class TestCollectChannelArtifacts:
    """Tests for _collect_channel_artifacts shareable artifact tracking."""

    def _call(self, event: dict, acc: StreamAccumulator) -> None:
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(event, acc)

    @patch("app.services.artifacts.share_token.is_shareable_artifact", return_value=True)
    def test_shareable_artifact_tracked(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
        f = tmp_path / "chart.html"
        f.write_text("<html></html>")
        acc = StreamAccumulator()
        event = {
            "data": [
                {
                    "id": "art-001",
                    "type": "text/html",
                    "file_path": str(f),
                    "filename": "chart.html",
                    "content_type": "text/html",
                }
            ]
        }
        self._call(event, acc)
        assert len(acc.file_attachments) == 1
        assert len(acc.shareable_artifacts) == 1
        sa = acc.shareable_artifacts[0]
        assert isinstance(sa, ShareableArtifact)
        assert sa.artifact_id == "art-001"
        assert sa.filename == "chart.html"
        assert sa.artifact_type == "text/html"

    @patch("app.services.artifacts.share_token.is_shareable_artifact", return_value=False)
    def test_non_shareable_not_tracked(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2")
        acc = StreamAccumulator()
        event = {
            "data": [
                {
                    "id": "art-002",
                    "type": "text/csv",
                    "file_path": str(f),
                    "filename": "data.csv",
                    "content_type": "text/csv",
                }
            ]
        }
        self._call(event, acc)
        assert len(acc.file_attachments) == 1
        assert len(acc.shareable_artifacts) == 0

    @patch("app.services.artifacts.share_token.is_shareable_artifact", return_value=True)
    def test_missing_artifact_id_not_tracked(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
        f = tmp_path / "page.html"
        f.write_text("<html></html>")
        acc = StreamAccumulator()
        event = {
            "data": [
                {
                    "file_path": str(f),
                    "filename": "page.html",
                    "content_type": "text/html",
                }
            ]
        }
        self._call(event, acc)
        assert len(acc.file_attachments) == 1
        assert len(acc.shareable_artifacts) == 0

    def test_empty_event_ignored(self):
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts({"data": []}, acc)
        assert len(acc.file_attachments) == 0
        collect_channel_artifacts({}, acc)
        assert len(acc.file_attachments) == 0


class TestBuildArtifactDeepLinks:
    """Tests for _build_artifact_deep_links URL generation."""

    @pytest.mark.asyncio
    async def test_empty_shareable_returns_empty(self):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        result = await build_artifact_deep_links(acc, [], "en")
        assert result == ()

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.artifact_deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="https://app.example.com",
    )
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="https://ingress.example.com",
    )
    @patch(
        "app.services.artifacts.share_token.create_artifact_share_token",
        return_value=("tok-abc123", 604800),
    )
    @patch(
        "app.channels.i18n.channel_t",
        return_value="View interactive page",
    )
    async def test_single_artifact_generates_button(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        media_list = [
            MediaAttachment(
                media_type=MediaType.DOCUMENT,
                path="/tmp/chart.html",
                filename="chart.html",
                mime_type="text/html",
            ),
        ]
        result = await build_artifact_deep_links(acc, media_list, "en")
        assert len(result) == 1
        buttons = result[0]
        assert len(buttons) == 1
        btn = buttons[0]
        assert btn.url == "https://app.example.com/public/artifact-share/tok-abc123"
        assert btn.label == "View interactive page"
        assert len(media_list) == 0

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.artifact_deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="https://app.example.com",
    )
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="",
    )
    async def test_no_version_returns_empty(
        self,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        result = await build_artifact_deep_links(acc, [], "en")
        assert result == ()

    @pytest.mark.asyncio
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no ingress"),
    )
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="",
    )
    async def test_no_base_url_safe_degradation(
        self,
        mock_base: MagicMock,
        mock_ingress: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        media_list = [
            MediaAttachment(
                media_type=MediaType.DOCUMENT,
                path="/tmp/chart.html",
                filename="chart.html",
                mime_type="text/html",
            ),
        ]
        result = await build_artifact_deep_links(acc, media_list, "en")
        assert result == ()
        assert len(media_list) == 1


    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.artifact_deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001", "art-002": "ver-002"},
    )
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="https://app.example.com",
    )
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="https://ingress.example.com",
    )
    @patch(
        "app.services.artifacts.share_token.create_artifact_share_token",
        return_value=("tok-multi", 604800),
    )
    @patch("app.channels.i18n.channel_t", side_effect=lambda _l, _k, **kw: kw.get("filename", "view"))
    async def test_multi_artifact_uses_named_label(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "a.html", "text/html"))
        acc.shareable_artifacts.append(ShareableArtifact("art-002", "b.pdf", "application/pdf"))
        media_list = [
            MediaAttachment(media_type=MediaType.DOCUMENT, path="/tmp/a.html", filename="a.html", mime_type="text/html"),
            MediaAttachment(media_type=MediaType.DOCUMENT, path="/tmp/b.pdf", filename="b.pdf", mime_type="application/pdf"),
            MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/photo.jpg", filename="photo.jpg", mime_type="image/jpeg"),
        ]
        result = await build_artifact_deep_links(acc, media_list, "zh")
        assert len(result) == 1
        buttons = result[0]
        assert len(buttons) == 2
        # channel_t called with artifact_deep_link_named for multi
        assert mock_t.call_args_list[0].args[1] == "artifact_deep_link_named"
        # Only non-linked attachment remains
        assert len(media_list) == 1
        assert media_list[0].filename == "photo.jpg"

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.artifact_deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-001": "ver-001"},
    )
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="https://app.example.com",
    )
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="",
    )
    @patch(
        "app.services.artifacts.share_token.create_artifact_share_token",
        side_effect=RuntimeError("HMAC key missing"),
    )
    @patch("app.channels.i18n.channel_t", return_value="view")
    async def test_token_generation_failure_skips_button(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(ShareableArtifact("art-001", "chart.html", "text/html"))
        media_list = [
            MediaAttachment(media_type=MediaType.DOCUMENT, path="/tmp/chart.html", filename="chart.html", mime_type="text/html"),
        ]
        result = await build_artifact_deep_links(acc, media_list, "en")
        # Token failed, no buttons generated, but media_list untouched
        assert result == ()
        assert len(media_list) == 1


class TestCollectMultipleArtifacts:
    """Edge cases for collecting multiple artifacts."""

    @patch("app.services.artifacts.share_token.is_shareable_artifact", return_value=True)
    def test_oversized_file_skipped(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
        f = tmp_path / "huge.html"
        f.write_bytes(b"x" * (6 * 1024 * 1024))  # 6MB > 5MB limit
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {"data": [{"id": "art-big", "type": "text/html", "file_path": str(f), "filename": "huge.html", "content_type": "text/html"}]},
            acc,
        )
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 0

    @patch("app.services.artifacts.share_token.is_shareable_artifact", return_value=True)
    def test_nonexistent_file_skipped(self, mock_shareable: MagicMock):  # noqa: ANN001
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {"data": [{"id": "art-ghost", "type": "text/html", "file_path": "/nonexistent/chart.html", "filename": "chart.html"}]},
            acc,
        )
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 0

    def test_invalid_data_types_skipped(self):
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts({"data": ["not_a_dict", 42, None]}, acc)
        assert len(acc.file_attachments) == 0


class TestFetchArtifactVersions:
    """Tests for _fetch_artifact_versions DB batch lookup."""

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            fetch_artifact_versions,
        )

        result = await fetch_artifact_versions([])
        assert result == {}

    @pytest.mark.asyncio
    @patch(
        "app.database.connection.get_session",
        side_effect=RuntimeError("DB unavailable"),
    )
    async def test_db_exception_returns_empty(self, mock_session: MagicMock):
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            fetch_artifact_versions,
        )

        result = await fetch_artifact_versions(["art-001"])
        assert result == {}


class TestCollectEmptyFileSkipped:
    """Zero-byte files must be skipped."""

    @patch("app.services.artifacts.share_token.is_shareable_artifact", return_value=True)
    def test_zero_byte_file_skipped(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
        f = tmp_path / "empty.html"
        f.write_bytes(b"")
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.artifact_deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {"data": [{"id": "art-empty", "type": "text/html", "file_path": str(f), "filename": "empty.html", "content_type": "text/html"}]},
            acc,
        )
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 0


class TestShareableArtifactNamedTuple:
    """Tests for ShareableArtifact NamedTuple."""

    def test_fields(self):
        sa = ShareableArtifact("id-1", "file.html", "text/html")
        assert sa.artifact_id == "id-1"
        assert sa.filename == "file.html"
        assert sa.artifact_type == "text/html"
        assert sa[0] == "id-1"
        assert sa[1] == "file.html"
        assert sa[2] == "text/html"

    def test_unpacking(self):
        sa = ShareableArtifact("id-1", "file.html", "text/html")
        aid, fname, atype = sa
        assert aid == "id-1"
        assert fname == "file.html"
        assert atype == "text/html"
