"""Cron deliverables: workspace files a cron result mentions ride along with its channel delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJob, DeliveryConfig, JobResult, JobType, Schedule

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ActionButton, ChannelCapabilities, OutboundMessage
from app.core.cron.adapters.channel_deliverables import CronDeliverables, collect_cron_deliverables
from app.core.cron.adapters.channel_delivery import ChannelResultDelivery

_HANDOFF_ROW = ((ActionButton(label="Continue in browser", action_id="web:continue_chat", url="https://myrm.example/chat-1"),),)


def _job(*, chat_id: str | None = "chat-1") -> CronJob:
    return CronJob(
        id="cron-deliverables",
        user_id="u1",
        name="weekly",
        job_type=JobType.AGENT,
        prompt="p",
        chat_id=chat_id,
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="feishu", target="chat-1"),
    )


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """A chat workspace on disk plus the three lookups the deliverables depend on."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = SimpleNamespace(
        workspace=workspace,
        root=AsyncMock(return_value=str(workspace)),
        locale=AsyncMock(return_value="en"),
        handoff=AsyncMock(return_value=_HANDOFF_ROW),
    )
    monkeypatch.setattr("app.core.channel_bridge.agent_executor.deliverable.resolve_chat_workspace_root", env.root)
    monkeypatch.setattr("app.core.channel_bridge.locale_provider.resolve_user_locale", env.locale)
    monkeypatch.setattr("app.remote_access.mobile_deep_link.resolve_web_handoff_components", env.handoff)
    return env


def _small_attachment_cap(monkeypatch: pytest.MonkeyPatch, limit: int) -> None:
    from app.core.channel_bridge.agent_executor.deliverable import scanner

    monkeypatch.setattr(scanner, "MAX_CHANNEL_ATTACHMENT_BYTES", limit)


def _spy_compressed_copies(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record the temp files the oversized-image compressor produces."""
    from app.core.channel_bridge.agent_executor.deliverable import scanner

    copies: list[Path] = []
    compress = scanner.compress_oversized_image

    def spy(src: str | Path, *, max_bytes: int) -> Path | None:
        copy = compress(src, max_bytes=max_bytes)
        if copy is not None:
            copies.append(copy)
        return copy

    monkeypatch.setattr(scanner, "compress_oversized_image", spy)
    return copies


def _write_noisy_png(path: Path) -> None:
    from PIL import Image

    Image.effect_noise((400, 400), 90).convert("RGB").save(path, format="PNG")


class TestCollectCronDeliverables:
    @pytest.mark.asyncio
    async def test_job_without_chat_has_no_workspace(self, env: SimpleNamespace) -> None:
        assert await collect_cron_deliverables(_job(chat_id=None), "See report.pdf") == CronDeliverables("See report.pdf")
        env.root.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_blank_output_is_not_scanned(self, env: SimpleNamespace) -> None:
        assert await collect_cron_deliverables(_job(), "  \n") == CronDeliverables("  \n")
        env.root.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_without_workspace_keeps_the_output(self, env: SimpleNamespace) -> None:
        env.root.return_value = None

        assert await collect_cron_deliverables(_job(), "See report.pdf") == CronDeliverables("See report.pdf")

    @pytest.mark.asyncio
    async def test_output_naming_no_workspace_file_is_untouched(self, env: SimpleNamespace) -> None:
        (env.workspace / "report.pdf").write_bytes(b"%PDF")

        out = await collect_cron_deliverables(_job(), "Nothing to attach, see missing.pdf")

        assert out == CronDeliverables("Nothing to attach, see missing.pdf")
        env.locale.assert_not_awaited()
        env.handoff.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mentioned_file_is_attached_with_web_handoff(self, env: SimpleNamespace) -> None:
        report = env.workspace / "report.pdf"
        report.write_bytes(b"%PDF-1.4")

        out = await collect_cron_deliverables(_job(), "Weekly report: report.pdf")

        assert out.content == "Weekly report:"
        assert [(m.filename, m.path, m.ephemeral) for m in out.media] == [("report.pdf", str(report.resolve()), False)]
        assert out.components == _HANDOFF_ROW
        assert out.locale == "en"
        env.handoff.assert_awaited_once_with("chat-1", locale="en")

    @pytest.mark.asyncio
    async def test_attachment_only_output_gets_a_localized_placeholder(self, env: SimpleNamespace) -> None:
        env.locale.return_value = "zh-CN"
        (env.workspace / "report.pdf").write_bytes(b"%PDF-1.4")

        out = await collect_cron_deliverables(_job(), "report.pdf")

        assert out.content == "交付物已附上。"
        assert len(out.media) == 1
        env.handoff.assert_awaited_once_with("chat-1", locale="zh-CN")

    @pytest.mark.asyncio
    async def test_oversized_file_is_noted_without_handoff(self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        _small_attachment_cap(monkeypatch, 100)
        (env.workspace / "big.pdf").write_bytes(b"%PDF-1.4" + b"x" * 500)

        out = await collect_cron_deliverables(_job(), "Done big.pdf")

        assert out.content == "Done\n\nbig.pdf (508 B) exceeds the channel attachment size limit and wasn't attached."
        assert out.media == ()
        assert out.components == ()
        assert out.locale == "en"
        env.handoff.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handoff_failure_still_attaches_the_file(self, env: SimpleNamespace) -> None:
        env.handoff.side_effect = RuntimeError("ingress down")
        (env.workspace / "report.pdf").write_bytes(b"%PDF-1.4")

        out = await collect_cron_deliverables(_job(), "report.pdf")

        assert len(out.media) == 1
        assert out.components == ()

    @pytest.mark.asyncio
    async def test_no_public_url_means_no_handoff_buttons(self, env: SimpleNamespace) -> None:
        env.handoff.return_value = ()
        (env.workspace / "report.pdf").write_bytes(b"%PDF-1.4")

        out = await collect_cron_deliverables(_job(), "report.pdf")

        assert len(out.media) == 1
        assert out.components == ()

    @pytest.mark.asyncio
    async def test_cancellation_discards_compressed_temp_files(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _small_attachment_cap(monkeypatch, 50_000)
        copies = _spy_compressed_copies(monkeypatch)
        _write_noisy_png(env.workspace / "chart.png")
        env.locale.side_effect = asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await collect_cron_deliverables(_job(), "Chart: chart.png")

        assert len(copies) == 1
        assert not copies[0].exists()


class _RecordingChannel(BaseChannel):
    name = "feishu"

    def __init__(self, capabilities: ChannelCapabilities) -> None:
        self.capabilities = capabilities
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "sent-1"


_RICH = ChannelCapabilities(media=True, file_upload=True, buttons=True)


@asynccontextmanager
async def _delivery_through(channel: BaseChannel, dlq_dir: Path) -> AsyncIterator[None]:
    import app.core.channel_bridge as channel_bridge

    gateway = ChannelGateway(dlq_dir=dlq_dir)
    gateway.register(channel)
    await gateway.start()
    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        yield
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()


class TestChannelResultDeliveryDeliverables:
    @pytest.mark.asyncio
    async def test_file_and_handoff_travel_with_the_message(self, env: SimpleNamespace, tmp_path: Path) -> None:
        report = env.workspace / "report.pdf"
        report.write_bytes(b"%PDF-1.4")
        channel = _RecordingChannel(_RICH)

        async with _delivery_through(channel, tmp_path / "dlq"):
            await ChannelResultDelivery().deliver(_job(), JobResult(success=True, output="Weekly report: report.pdf"))

        (sent,) = channel.sent
        assert sent.content == "Weekly report:"
        assert [m.filename for m in sent.media] == ["report.pdf"]
        assert sent.components == _HANDOFF_ROW
        assert sent.metadata is not None
        assert sent.metadata["locale"] == "en"
        assert report.exists()  # a workspace file is the user's, never the bus's to delete

    @pytest.mark.asyncio
    async def test_error_text_follows_the_deliverables(self, env: SimpleNamespace, tmp_path: Path) -> None:
        (env.workspace / "report.pdf").write_bytes(b"%PDF-1.4")
        channel = _RecordingChannel(_RICH)

        async with _delivery_through(channel, tmp_path / "dlq"):
            await ChannelResultDelivery().deliver(_job(), JobResult(success=False, output="Partial report.pdf", error="boom"))

        (sent,) = channel.sent
        assert sent.content == "Partial\n\n**Error:** boom"
        assert [m.filename for m in sent.media] == ["report.pdf"]

    @pytest.mark.asyncio
    async def test_text_only_route_keeps_a_note_and_a_link(self, env: SimpleNamespace, tmp_path: Path) -> None:
        (env.workspace / "report.pdf").write_bytes(b"%PDF-1.4")
        channel = _RecordingChannel(ChannelCapabilities())

        async with _delivery_through(channel, tmp_path / "dlq"):
            await ChannelResultDelivery().deliver(_job(), JobResult(success=True, output="Weekly report: report.pdf"))

        (sent,) = channel.sent
        assert sent.media == ()
        assert sent.components == ()
        assert "Attachment not sent: report.pdf" in sent.content
        assert "Continue in browser → https://myrm.example/chat-1" in sent.content

    @pytest.mark.asyncio
    async def test_compressed_copy_is_deleted_once_delivered(
        self, env: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _small_attachment_cap(monkeypatch, 50_000)
        copies = _spy_compressed_copies(monkeypatch)
        chart = env.workspace / "chart.png"
        _write_noisy_png(chart)
        channel = _RecordingChannel(_RICH)

        async with _delivery_through(channel, tmp_path / "dlq"):
            await ChannelResultDelivery().deliver(_job(), JobResult(success=True, output="Chart: chart.png"))

        (sent,) = channel.sent
        assert [m.ephemeral for m in sent.media] == [True]
        assert len(copies) == 1
        assert not copies[0].exists()
        assert chart.exists()

    @pytest.mark.asyncio
    async def test_revoked_identity_is_rejected_before_any_file_is_collected(
        self, env: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.core.channel_bridge.topic_config.SqlTopicManager.resolve_topic",
            AsyncMock(return_value=SimpleNamespace(identity_revoked=True)),
        )
        (env.workspace / "report.pdf").write_bytes(b"%PDF-1.4")
        channel = _RecordingChannel(_RICH)

        async with _delivery_through(channel, tmp_path / "dlq"):
            with pytest.raises(RuntimeError, match="identity revoked"):
                await ChannelResultDelivery().deliver(_job(), JobResult(success=True, output="report.pdf"))

        assert channel.sent == []
        env.root.assert_not_awaited()
