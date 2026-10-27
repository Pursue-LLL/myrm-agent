"""Delegation replies reach the sender in the sender's own language.

[INPUT]
- app.channels.routing.router::AgentRouter (real router over a stub bus)
- app.channels.i18n locale catalog (en, zh-CN, ja)

[OUTPUT]
- Tests that the four replies of the ``/delegate`` flow (missing task, quota reached, receipt, steering injected)
  follow the message locale, with the zh-CN texts asserted verbatim.

[POS]
Server tests for the channel router's delegation branch.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, OutboundMessage
from tests.support.risk_gate import build_service_with_rules

_DETECTION = "app.services.risk.detection.get_detection_service"
_CJK = re.compile(r"[぀-ヿ㐀-鿿]")


@dataclass
class _Rig:
    router: AgentRouter
    bus: MagicMock

    def sent(self) -> list[OutboundMessage]:
        return [call.args[0] for call in self.bus.publish_outbound.await_args_list]

    def only_reply(self) -> str:
        sent = self.sent()
        assert len(sent) == 1, f"expected one reply, got {len(sent)}"
        return str(sent[0].content)


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> _Rig:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    monkeypatch.setattr(AgentRouter, "_check_admin_permission", AsyncMock(return_value=True))
    router = AgentRouter(bus=bus, pairing_store=MagicMock(), agent_executor=MagicMock())
    return _Rig(router=router, bus=bus)


def _message(content: str, locale: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        user_id="u1",
        chat_id="chat-1",
        content=content,
        message_id="m1",
        metadata={"locale": locale},
    )


async def _consume_one(rig: _Rig, msg: InboundMessage) -> None:
    rig.router._running = True
    rig.bus.consume_inbound = AsyncMock(side_effect=[msg, asyncio.CancelledError])
    with patch(_DETECTION, return_value=build_service_with_rules([])):
        await rig.router._consume_loop()
    await asyncio.sleep(0)  # the router publishes these replies from a spawned task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Add the task after the delegate command"),
        ("zh-CN", "请在委派指令后附带具体任务内容"),
        ("ja", "委任コマンドの後に具体的なタスク内容を付けてください"),
    ],
)
async def test_a_delegate_command_without_a_task_is_answered_in_the_senders_language(
    rig: _Rig, locale: str, expected: str
) -> None:
    await _consume_one(rig, _message("/delegate ", locale))

    assert expected in rig.only_reply()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "2 background tasks are already running"),
        ("zh-CN", "当前已有 2 个后台长任务正在执行中"),
        ("ja", "バックグラウンドタスクがすでに 2 件実行中"),
    ],
)
async def test_the_quota_reply_states_the_real_limit_in_the_senders_language(rig: _Rig, locale: str, expected: str) -> None:
    for task_id in ("busy-1", "busy-2"):
        rig.router._delegation_guard.acquire("telegram", "u1", task_id)

    assert await rig.router._handle_delegation_inbound(_message("/delegate third", locale), "third") is True

    assert expected in rig.only_reply()


@pytest.mark.asyncio
async def test_the_quota_reply_follows_the_configured_limit(rig: _Rig) -> None:
    rig.router._delegation_guard.max_active = 3
    for task_id in ("busy-1", "busy-2", "busy-3"):
        rig.router._delegation_guard.acquire("telegram", "u1", task_id)

    await rig.router._handle_delegation_inbound(_message("/delegate fourth", "en"), "fourth")

    assert "3 background tasks are already running" in rig.only_reply()


@pytest.mark.asyncio
async def test_the_receipt_is_in_english_for_an_english_sender_and_keeps_the_task_and_its_id(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rig.router._delegation_coordinator, "execute_task_lifecycle", AsyncMock())

    await rig.router._handle_delegation_inbound(_message("/delegate draft the Q3 summary", "en"), "draft the Q3 summary")
    await asyncio.sleep(0)

    receipt = rig.sent()[0]
    assert receipt.metadata is not None
    assert "Delegated task received" in str(receipt.content)
    assert "draft the Q3 summary" in str(receipt.content)
    assert f"[{receipt.metadata['delegation_task_id']}]" in str(receipt.content)
    assert receipt.metadata["is_receipt"] is True
    assert _CJK.search(str(receipt.content)) is None


@pytest.mark.asyncio
async def test_the_chinese_receipt_names_the_task_and_what_happens_next(rig: _Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rig.router._delegation_coordinator, "execute_task_lifecycle", AsyncMock())

    await rig.router._handle_delegation_inbound(_message("/delegate 做季度总结", "zh-CN"), "做季度总结")
    await asyncio.sleep(0)

    receipt = rig.sent()[0]
    assert receipt.metadata is not None
    task_id = receipt.metadata["delegation_task_id"]
    assert receipt.content == (
        f"📋 **已收到异步任务委派** `[{task_id}]`\n\n"
        "💡 **任务内容**：做季度总结\n"
        "⏳ **状态**：后台沙箱自主接管中，您可以放心退出聊天，执行完成后将自动把结果发到这里。如果某一步需要您批准，会在这里询问您。\n"
        "*(提示：中途可直接发送消息为任务补充指引，发送 /stop 可取消任务)*"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "Your extra guidance was passed to background task `[t-1]`"),
        ("zh-CN", "已将补充指引动态注入后台任务 `[t-1]`"),
        ("ja", "追加の指示をバックグラウンドタスク `[t-1]` に反映しました"),
    ],
)
async def test_steering_a_delegated_task_is_acknowledged_in_the_senders_language(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch, locale: str, expected: str
) -> None:
    coordinator = MagicMock()
    coordinator.find_active_task.return_value = SimpleNamespace(task_id="t-1")
    coordinator.inject_steering.return_value = True
    monkeypatch.setattr(rig.router, "_delegation_coordinator", coordinator)

    await _consume_one(rig, _message("also use the Q3 numbers", locale))

    coordinator.inject_steering.assert_called_once()
    assert expected in rig.only_reply()
