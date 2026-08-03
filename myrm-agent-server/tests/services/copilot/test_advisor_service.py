from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.streaming.run_digest import RunDigestPhase, build_run_digest

from app.services.copilot.advisor_service import ask_advisor
from app.services.copilot.run_digest_store import RunDigestStore


def setup_method() -> None:
    RunDigestStore._digests.clear()
    RunDigestStore._sessions.clear()


@pytest.mark.asyncio
async def test_tier0_status_question_zh() -> None:
    digest = build_run_digest(
        chat_id="chat-zh",
        progress_steps=[{"tool_name": "grep", "step_key": "g1"}],
        phase=RunDigestPhase.RUNNING,
    )
    RunDigestStore._digests["chat-zh"] = digest

    reply, tier = await ask_advisor(
        chat_id="chat-zh",
        question="现在在干嘛？",
        accept_language="zh-CN",
    )
    assert tier == "tier0"
    assert "步骤 1" in reply


@pytest.mark.asyncio
async def test_tier0_status_question() -> None:
    digest = build_run_digest(
        chat_id="chat-1",
        progress_steps=[{"tool_name": "grep", "step_key": "g1"}],
        phase=RunDigestPhase.RUNNING,
        elapsed_seconds=5,
    )
    RunDigestStore._digests["chat-1"] = digest

    reply, tier = await ask_advisor(chat_id="chat-1", question="现在在干嘛？")
    assert tier == "tier0"
    assert "Step 1: grep" in reply


@pytest.mark.asyncio
async def test_tier1_when_no_status_pattern() -> None:
    digest = build_run_digest(
        chat_id="chat-2",
        progress_steps=[],
        phase=RunDigestPhase.IDLE,
    )
    RunDigestStore._digests["chat-2"] = digest

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Custom answer."))]

    with (
        patch(
            "app.services.copilot.advisor_service.load_user_configs",
            new=AsyncMock(
                return_value=MagicMock(
                    providers_dict={"openai": {}},
                    model_cfg=MagicMock(model="gpt-test", api_key="k", base_url=None),
                )
            ),
        ),
        patch("litellm.acompletion", new=AsyncMock(return_value=mock_response)),
    ):
        reply, tier = await ask_advisor(chat_id="chat-2", question="Explain the last tool output")

    assert tier == "tier1"
    assert reply == "Custom answer."
