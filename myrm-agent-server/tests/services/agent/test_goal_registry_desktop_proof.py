"""Goal evaluator desktop proof: the evaluator observes the screen but never unlocks it.

[INPUT]
- app.services.agent.goals.goal_registry（POS: ServerGoalManager.evaluate_semantic 的桌面截图分支）
- myrm_agent_harness.api.security（POS: ScreenLockState / get_default_screen_detector 探针）

[OUTPUT]
- 锁屏/休眠态降级为纯文本判定且不触发解锁；已解锁/未知态取图
- 结构契约：解锁只由 unattended watcher 发起，评估器与其余业务代码不得调用 MacScreenUnlocker.unlock

[POS]
评估器（无人值守 Goal 的语义裁判）对桌面画面只读：解锁决策（在场探针 + 租约位）只在 watcher 一处。
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from myrm_agent_harness.api.security import ScreenLockState

from app.services.agent.goals.goal_registry import ServerGoalManager
from app.services.locked_use.service import MacScreenUnlocker

APP_ROOT = Path(__file__).resolve().parents[3] / "app"
GOAL_REGISTRY = APP_ROOT / "services" / "agent" / "goals" / "goal_registry.py"
UNATTENDED = APP_ROOT / "services" / "locked_use" / "unattended.py"


class _DesktopToolMessage:
    type = "tool"
    name = "desktop_snapshot_tool"


async def _evaluate(state: ScreenLockState) -> tuple[list[object], AsyncMock]:
    """Run one semantic evaluation with a desktop session attached and the screen in ``state``."""
    manager = ServerGoalManager(AsyncMock(), session_id="desktop-session")

    desktop_session = MagicMock()
    desktop_session.take_screenshot = AsyncMock(return_value=SimpleNamespace(success=True, screenshot_base64="desktop_b64"))
    gateway = MagicMock()
    gateway.get_active_browser_session.return_value = None
    gateway.get_active_desktop_session.return_value = desktop_session

    detector = MagicMock()
    detector.get_state.return_value = state

    captured: list[object] = []

    async def ainvoke(messages: list[object], **_: object) -> MagicMock:
        captured.extend(messages)
        response = MagicMock()
        response.content = '{"done": false, "reason": "x"}'
        return response

    llm = MagicMock()
    llm.ainvoke = ainvoke

    with (
        patch("app.services.agent.gateway.get_agent_gateway", return_value=gateway),
        patch("app.services.agent.platform_config.load_platform_llm", new=AsyncMock(return_value=llm)),
        patch("myrm_agent_harness.api.security.get_default_screen_detector", return_value=detector),
        patch.object(MacScreenUnlocker, "unlock", new_callable=AsyncMock) as unlock,
    ):
        await manager.evaluate_semantic("criteria", "content", context_messages=[_DesktopToolMessage()])
        unlock.assert_not_awaited()

    return captured, desktop_session.take_screenshot


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [ScreenLockState.LOCKED, ScreenLockState.SLEEPING])
async def test_locked_or_sleeping_screen_degrades_to_text_only_without_unlocking(state: ScreenLockState) -> None:
    captured, take_screenshot = await _evaluate(state)

    user_msg = next(m for m in captured if isinstance(m, HumanMessage))
    assert user_msg.content == "content"
    take_screenshot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [ScreenLockState.UNLOCKED, ScreenLockState.UNKNOWN])
async def test_available_screen_is_captured_as_visual_proof(state: ScreenLockState) -> None:
    captured, take_screenshot = await _evaluate(state)

    user_msg = next(m for m in captured if isinstance(m, HumanMessage))
    assert isinstance(user_msg.content, list)
    assert "desktop_b64" in user_msg.content[1]["image_url"]["url"]
    take_screenshot.assert_awaited_once()


def _unlock_call_sites() -> list[Path]:
    """Every app module that references ``MacScreenUnlocker.unlock``."""
    sites: list[Path] = []
    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "unlock"
                and isinstance(node.value, ast.Name)
                and node.value.id == "MacScreenUnlocker"
            ):
                sites.append(path)
                break
    return sites


def test_only_the_unattended_watcher_initiates_an_unlock() -> None:
    assert _unlock_call_sites() == [UNATTENDED]


def test_goal_evaluator_does_not_depend_on_the_unlock_machinery() -> None:
    tree = ast.parse(GOAL_REGISTRY.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert not {m for m in imported if m.startswith("app.services.locked_use")}
