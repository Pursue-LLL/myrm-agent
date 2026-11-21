"""Unit tests for collecting deliverable artifacts from harness stream events into the accumulator."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
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

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=False)
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

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
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
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts({"data": []}, acc)
        assert len(acc.file_attachments) == 0
        collect_channel_artifacts({}, acc)
        assert len(acc.file_attachments) == 0


class TestCollectMultipleArtifacts:
    """Edge cases for collecting multiple artifacts."""

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
    def test_oversized_shareable_tracked_with_fallback_note(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
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
        # Oversized shareable artifacts are both deep-linked AND carry a note,
        # so a share link that cannot be built or opened still names the file.
        assert len(acc.file_attachments) == 0
        assert len(acc.shareable_artifacts) == 1
        assert acc.oversized_deliverables == [("huge.html", "6.0 MB")]

    @pytest.mark.asyncio
    @patch(
        "app.remote_access.mobile_deep_link.resolve_mobile_remote_base_url",
        return_value="",
    )
    async def test_deep_link_failure_keeps_fallback_note(self, mock_base: MagicMock):  # noqa: ANN001
        """No public base URL → no button, but the fallback note survives."""
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            build_artifact_deep_links,
        )

        acc = StreamAccumulator()
        acc.shareable_artifacts.append(
            ShareableArtifact("art-001", "report.pdf", "application/pdf"),
        )
        acc.oversized_deliverables.append(("report.pdf", "8.0 MB"))
        buttons = await build_artifact_deep_links(acc, "en")
        assert buttons == ()
        # Note must stay present when no button was produced.
        assert acc.oversized_deliverables == [("report.pdf", "8.0 MB")]

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=False)
    def test_oversized_non_shareable_reported(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
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

    def test_oversized_image_compressed_into_attachment(self, tmp_path, monkeypatch):  # noqa: ANN001
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
        assert acc.file_attachments[0].ephemeral is True  # compressed temp file is bus-owned
        assert acc.oversized_deliverables == []
        assert len(acc.compressed_deliverables) == 1
        assert acc.compressed_deliverables[0][0] == "huge.png"
        Path(acc.file_attachments[0].path).unlink(missing_ok=True)

    def test_oversized_webp_compressed_filename_aligned(self, tmp_path, monkeypatch):  # noqa: ANN001
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
        assert acc.file_attachments[0].ephemeral is True
        Path(acc.file_attachments[0].path).unlink(missing_ok=True)

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
    def test_nonexistent_file_skipped(self, mock_shareable: MagicMock, caplog: pytest.LogCaptureFixture):  # noqa: ANN001
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
        assert any("Skipping artifact with missing file_path" in record.message for record in caplog.records)

    def test_invalid_data_types_skipped(self):
        acc = StreamAccumulator()
        from app.core.channel_bridge.agent_executor.deliverable.deep_links import (
            collect_channel_artifacts,
        )

        collect_channel_artifacts({"data": ["not_a_dict", 42, None]}, acc)
        assert len(acc.file_attachments) == 0

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
    def test_non_string_file_path_skipped(self, mock_shareable: MagicMock):  # noqa: ANN001
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

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
    def test_getsize_oserror_skipped(self, mock_shareable: MagicMock, tmp_path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001
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


class TestCollectEmptyFileSkipped:
    """Zero-byte files must be skipped."""

    @patch("app.services.artifacts.share.share_token.is_shareable_artifact", return_value=True)
    def test_zero_byte_file_skipped(self, mock_shareable: MagicMock, tmp_path):  # noqa: ANN001
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
