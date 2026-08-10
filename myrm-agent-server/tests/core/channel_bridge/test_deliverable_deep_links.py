"""Unit tests for artifact deep link injection in ChannelAgentExecutor.

Tests collect_channel_artifacts shareable artifact tracking,
build_artifact_deep_links URL generation + linked-filename reporting,
and _fetch_artifact_versions DB batch lookup.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.executor_helpers import (
    ShareableArtifact,
    StreamAccumulator,
)


class TestCollectChannelArtifacts:
    """Tests for collect_channel_artifacts shareable artifact tracking."""

    def _call(self, event: dict, acc: StreamAccumulator) -> None:
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(event, acc)

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_shareable_artifact_tracked(
        self, mock_shareable: MagicMock, tmp_path
    ):  # noqa: ANN001
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

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=False
    )
    def test_non_shareable_not_tracked(
        self, mock_shareable: MagicMock, tmp_path
    ):  # noqa: ANN001
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

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_missing_artifact_id_not_tracked(
        self, mock_shareable: MagicMock, tmp_path
    ):  # noqa: ANN001
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
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts({"data": []}, acc)
        assert len(acc.file_attachments) == 0
        collect_channel_artifacts({}, acc)
        assert len(acc.file_attachments) == 0


class TestBuildArtifactDeepLinks:
    """Tests for build_artifact_deep_links URL generation."""

    @pytest.mark.asyncio
    async def test_empty_shareable_returns_empty(self):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert buttons == ()
        assert linked == frozenset()

    @pytest.mark.asyncio
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="",
    )
    @patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        new_callable=AsyncMock,
        return_value="",
    )
    async def test_missing_ingress_logs_warning(
        self,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
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
            buttons, linked = await build_artifact_deep_links(acc, "en")

        assert buttons == ()
        assert linked == frozenset()
        assert any(
            "no public ingress base URL" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
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
        return_value="https://ingress.example.com",
    )
    async def test_empty_version_map_logs_warning(
        self,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
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
            buttons, linked = await build_artifact_deep_links(acc, "en")

        assert buttons == ()
        assert linked == frozenset()
        assert any(
            "no artifact versions found" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
        new_callable=AsyncMock,
        return_value={"art-partial": "ver-partial"},
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
        return_value=("token-abc", 9999999999),
    )
    async def test_missing_version_id_logs_warning(
        self,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
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
            buttons, linked = await build_artifact_deep_links(acc, "en")

        assert len(buttons) == 1
        assert linked == frozenset({"report.html"})
        assert any(
            "no version_id in DB" in record.message and "art-missing" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
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
    async def test_artifact_without_version_skipped(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
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
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert len(buttons) == 1
        assert linked == frozenset({"chart.html"})
        btn = buttons[0]
        assert btn.url == "https://app.example.com/public/artifact-share/tok-abc123"
        assert btn.label == "View interactive page"

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
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
    async def test_single_artifact_uses_default_label(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
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
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert len(buttons) == 1
        assert linked == frozenset({"chart.html"})
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
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
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
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert buttons == ()
        assert linked == frozenset()

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
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
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert buttons == ()
        assert linked == frozenset()

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
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html"),
        )
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert buttons == ()
        assert linked == frozenset()

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
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
    @patch(
        "app.channels.i18n.channel_t",
        side_effect=lambda _l, _k, **kw: kw.get("filename", "view"),
    )
    async def test_multi_artifact_uses_named_label(
        self,
        mock_t: MagicMock,
        mock_token: MagicMock,
        mock_ingress: AsyncMock,
        mock_base: MagicMock,
        mock_versions: AsyncMock,
    ):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "a.html", "text/html")
        )
        acc.shareable_artifacts.append(
            ShareableArtifact("art-002", "b.pdf", "application/pdf")
        )
        buttons, linked = await build_artifact_deep_links(acc, "zh")
        assert len(buttons) == 2
        # channel_t called with artifact_deep_link_named for multi
        assert mock_t.call_args_list[0].args[1] == "artifact_deep_link_named"
        assert linked == frozenset({"a.html", "b.pdf"})

    @pytest.mark.asyncio
    @patch(
        "app.core.channel_bridge.agent_executor.deliverable.deep_links.fetch_artifact_versions",
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
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "chart.html", "text/html")
        )
        buttons, linked = await build_artifact_deep_links(acc, "en")
        # Token failed, no buttons generated, nothing linked.
        assert buttons == ()
        assert linked == frozenset()


class TestCollectMultipleArtifacts:
    """Edge cases for collecting multiple artifacts."""

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_oversized_shareable_tracked_with_fallback_note(
        self, mock_shareable: MagicMock, tmp_path
    ):  # noqa: ANN001
        f = tmp_path / "huge.html"
        f.write_bytes(b"x" * (6 * 1024 * 1024))  # 6MB > 5MB limit
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-big",
                        "type": "text/html",
                        "file_path": str(f),
                        "filename": "huge.html",
                        "content_type": "text/html",
                    }
                ]
            },
            acc,
        )
        # Oversized shareable artifacts are both deep-linked AND carry a fallback
        # note, so a failed deep-link build still surfaces the file to the user.
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 1
        assert acc.oversized_deliverables == [("huge.html", "6.0 MB")]

    @pytest.mark.asyncio
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="",
    )
    async def test_deep_link_failure_keeps_fallback_note(
        self, mock_base: MagicMock
    ):  # noqa: ANN001
        """No public base URL → no button, but the fallback note survives."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "report.pdf", "application/pdf"),
        )
        acc.oversized_deliverables.append(("report.pdf", "8.0 MB"))
        buttons, linked = await build_artifact_deep_links(acc, "en")
        assert buttons == ()
        assert linked == frozenset()
        # Note must stay present when no button was produced.
        assert acc.oversized_deliverables == [("report.pdf", "8.0 MB")]

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=False
    )
    def test_oversized_non_shareable_reported(
        self, mock_shareable: MagicMock, tmp_path
    ):  # noqa: ANN001
        f = tmp_path / "huge.csv"
        f.write_bytes(b"x" * (6 * 1024 * 1024))  # 6MB > 5MB limit
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-big",
                        "type": "text/csv",
                        "file_path": str(f),
                        "filename": "huge.csv",
                        "content_type": "text/csv",
                    }
                ]
            },
            acc,
        )
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 0
        assert acc.oversized_deliverables == [("huge.csv", "6.0 MB")]

    def test_oversized_image_compressed_into_attachment(
        self, tmp_path, monkeypatch
    ):  # noqa: ANN001
        from PIL import Image

        from app.core.channel_bridge.agent_executor.deliverable import deep_links

        monkeypatch.setattr(deep_links, "MAX_CHANNEL_ATTACHMENT_BYTES", 50_000)
        img = tmp_path / "huge.png"
        Image.effect_noise((400, 400), 90).convert("RGB").save(img, format="PNG")
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-img",
                        "type": "image/png",
                        "file_path": str(img),
                        "filename": "huge.png",
                        "content_type": "image/png",
                    }
                ]
            },
            acc,
        )
        assert len(acc.file_attachments) == 1
        assert acc.file_attachments[0].filename == "huge.png"
        assert acc.file_attachments[0].mime_type == "image/png"
        assert len(acc.pending_tmp_paths) == 1
        assert acc.oversized_deliverables == []
        assert len(acc.compressed_deliverables) == 1
        assert acc.compressed_deliverables[0][0] == "huge.png"
        for p in acc.pending_tmp_paths:
            Path(p).unlink(missing_ok=True)

    def test_oversized_webp_compressed_filename_aligned(
        self, tmp_path, monkeypatch
    ):  # noqa: ANN001
        from PIL import Image

        from app.core.channel_bridge.agent_executor.deliverable import deep_links

        monkeypatch.setattr(deep_links, "MAX_CHANNEL_ATTACHMENT_BYTES", 50_000)
        img = tmp_path / "hero.webp"
        Image.effect_noise((400, 400), 90).convert("RGB").save(img, format="WEBP")
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-webp",
                        "type": "image/webp",
                        "file_path": str(img),
                        "filename": "hero.webp",
                        "content_type": "image/webp",
                    }
                ]
            },
            acc,
        )
        assert len(acc.file_attachments) == 1
        assert acc.file_attachments[0].filename == "hero.jpg"
        assert acc.file_attachments[0].mime_type == "image/jpeg"
        assert acc.file_attachments[0].path.endswith(".jpg")
        for p in acc.pending_tmp_paths:
            Path(p).unlink(missing_ok=True)

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_nonexistent_file_skipped(
        self, mock_shareable: MagicMock, caplog: pytest.LogCaptureFixture
    ):  # noqa: ANN001
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        with caplog.at_level(logging.WARNING):
            collect_channel_artifacts(
                {
                    "data": [
                        {
                            "id": "art-ghost",
                            "type": "text/html",
                            "file_path": "/nonexistent/chart.html",
                            "filename": "chart.html",
                        }
                    ]
                },
                acc,
            )
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 0
        assert any(
            "Skipping artifact with missing file_path" in record.message
            for record in caplog.records
        )

    def test_invalid_data_types_skipped(self):
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts({"data": ["not_a_dict", 42, None]}, acc)
        assert len(acc.file_attachments) == 0

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_non_string_file_path_skipped(
        self, mock_shareable: MagicMock
    ):  # noqa: ANN001
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-x",
                        "type": "text/html",
                        "file_path": 12345,
                        "filename": "x.html",
                    }
                ]
            },
            acc,
        )
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 0

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_getsize_oserror_skipped(
        self, mock_shareable: MagicMock, tmp_path, monkeypatch: pytest.MonkeyPatch
    ):  # noqa: ANN001
        f = tmp_path / "race.html"
        f.write_text("<html></html>")
        monkeypatch.setattr(
            "app.core.channel_bridge.agent_executor.deliverable.deep_links.os.path.getsize",
            lambda _p: (_ for _ in ()).throw(OSError("gone")),
        )
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-race",
                        "type": "text/html",
                        "file_path": str(f),
                        "filename": "race.html",
                    }
                ]
            },
            acc,
        )
        assert len(acc.file_attachments) == 0


class TestFetchArtifactVersions:
    """Tests for fetch_artifact_versions DB batch lookup."""

    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
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
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            fetch_artifact_versions,
        )

        result = await fetch_artifact_versions(["art-001"])
        assert result == {}

    @pytest.mark.asyncio
    async def test_real_db_latest_version_selected(self) -> None:
        """Real SQLite lookup picks the newest version per artifact."""
        from contextlib import asynccontextmanager
        from unittest.mock import patch

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            fetch_artifact_versions,
        )
        from app.database.models import Base
        from app.database.models.artifact import Artifact, ArtifactVersion

        engine = create_async_engine(
            "sqlite+aiosqlite:///file:deep_links_test?mode=memory&cache=shared&uri=true"
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as db:
            db.add_all(
                [
                    Artifact(
                        id="art-1",
                        name="report",
                        versions=[
                            ArtifactVersion(
                                id="v-old",
                                vault_uri="vault://old",
                                sha256_hash="a" * 64,
                            ),
                            ArtifactVersion(
                                id="v-new",
                                vault_uri="vault://new",
                                sha256_hash="b" * 64,
                            ),
                        ],
                    ),
                    Artifact(
                        id="art-2",
                        name="notes",
                        versions=[
                            ArtifactVersion(
                                id="v-solo",
                                vault_uri="vault://solo",
                                sha256_hash="c" * 64,
                            ),
                        ],
                    ),
                    Artifact(
                        id="art-3",
                        name="no versions",
                        versions=[],
                    ),
                    Artifact(
                        id="art-4",
                        name="deleted",
                        is_deleted=True,
                        versions=[
                            ArtifactVersion(
                                id="v-del",
                                vault_uri="vault://del",
                                sha256_hash="d" * 64,
                            ),
                        ],
                    ),
                ]
            )
            await db.commit()

            # Give the two versions distinct creation times so the max pick is deterministic.
            stmt = select(ArtifactVersion).where(
                ArtifactVersion.artifact_id == "art-1"
            )
            rows = (await db.execute(stmt)).scalars().all()
            import datetime

            rows[0].created_at = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
            rows[1].created_at = datetime.datetime(2025, 6, 1, tzinfo=datetime.timezone.utc)
            await db.commit()

            @asynccontextmanager
            async def fake_get_session():
                yield db

            with patch(
                "app.database.connection.get_session", new=fake_get_session
            ):
                result = await fetch_artifact_versions(
                    ["art-1", "art-2", "art-3", "art-4"]
                )

        assert result == {"art-1": "v-new", "art-2": "v-solo"}
        await engine.dispose()


class TestCollectEmptyFileSkipped:
    """Zero-byte files must be skipped."""

    @patch(
        "app.services.artifacts.share_token.is_shareable_artifact", return_value=True
    )
    def test_zero_byte_file_skipped(
        self, mock_shareable: MagicMock, tmp_path
    ):  # noqa: ANN001
        f = tmp_path / "empty.html"
        f.write_bytes(b"")
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts(
            {
                "data": [
                    {
                        "id": "art-empty",
                        "type": "text/html",
                        "file_path": str(f),
                        "filename": "empty.html",
                        "content_type": "text/html",
                    }
                ]
            },
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
