from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionRequest,
    EvolutionStrategy,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.pipeline.confirmation import extract_error_signals
from myrm_agent_harness.agent.skills.evolution.pipeline.screener import EvolutionScreener

_CODE = "def test():\n    pass"
_UNLOCKED_MD = "---\nname: test_skill\ndescription: Demo.\n---\nBody as the file has it.\n"
_LOCKED_MD = "---\nname: test_skill\ndescription: Demo.\nevolution-locked: true\n---\nBody as the file has it.\n"


def _skill_record(content: str = _CODE, path: str = "") -> SkillRecord:
    return SkillRecord(
        skill_id="test_skill",
        name="test_skill",
        description="Demo.",
        content=content,
        path=path,
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
        updated_at=datetime.now() - timedelta(seconds=4000),  # Pass cooldown
    )


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.is_evolution_locked.return_value = False
    store.get_skill.return_value = _skill_record()
    store.load_rejections.return_value = []

    return store


@pytest.fixture
def write_skill_file(tmp_path: Path) -> Callable[[str], str]:
    def write(text: str) -> str:
        path = tmp_path / "SKILL.md"
        path.write_text(text, encoding="utf-8")
        return str(path)

    return write


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    # default to YES
    response = MagicMock()
    response.content = "YES"
    llm.ainvoke.return_value = response
    return llm


@pytest.mark.asyncio
async def test_screener_no_skill_id(mock_store):
    screener = EvolutionScreener(store=mock_store)
    request = EvolutionRequest(evolution_type=EvolutionType.FIX, skill_id="")

    result = await screener.screen_request(request)
    assert result.allowed is True
    assert result.phase == "none"


@pytest.mark.asyncio
async def test_screener_locked_skill(mock_store):
    mock_store.is_evolution_locked.return_value = True
    screener = EvolutionScreener(store=mock_store)
    request = EvolutionRequest(evolution_type=EvolutionType.FIX, skill_id="test_skill")

    result = await screener.screen_request(request)
    assert result.allowed is False
    assert result.phase == "locked"
    mock_store.get_skill.assert_not_called()  # the store's flag decides without reading the skill or its file


@pytest.mark.asyncio
async def test_screener_static_interception(mock_store):
    screener = EvolutionScreener(store=mock_store)
    # Give it an error reason that triggers static interception
    request = EvolutionRequest(
        evolution_type=EvolutionType.FIX,
        skill_id="test_skill",
        reason="Traceback (most recent call last):\nTypeError: unsupported operand type(s) for +",
    )

    result = await screener.screen_request(request)
    assert result.allowed is True
    assert result.phase == "static_interception"


@pytest.mark.asyncio
async def test_screener_llm_confirmation_yes(mock_store, mock_llm):
    screener = EvolutionScreener(store=mock_store, cheap_llm=mock_llm)
    # Generic error that doesn't trigger static interception
    request = EvolutionRequest(
        evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="CustomError: something went wrong"
    )

    result = await screener.screen_request(request)
    assert result.allowed is True
    assert result.phase == "llm_confirmation"


@pytest.mark.asyncio
async def test_screener_llm_confirmation_no(mock_store, mock_llm):
    # Setup LLM to return NO
    response = MagicMock()
    response.content = "NO: network error"
    mock_llm.ainvoke.return_value = response

    screener = EvolutionScreener(store=mock_store, cheap_llm=mock_llm)
    request = EvolutionRequest(
        evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="HTTP 500: Internal Server Error"
    )

    result = await screener.screen_request(request)
    assert result.allowed is False
    assert result.phase == "llm_confirmation"


@pytest.mark.asyncio
async def test_screener_llm_confirmation_json(mock_store, mock_llm):
    # Setup LLM to return JSON
    response = MagicMock()
    response.content = '{"approved": true, "reason": "logic error", "confidence": 0.9}'
    mock_llm.ainvoke.return_value = response

    screener = EvolutionScreener(store=mock_store, cheap_llm=mock_llm)
    request = EvolutionRequest(
        evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="Exception: division by zero"
    )

    result = await screener.screen_request(request)
    assert result.allowed is True
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_screener_llm_confirmation_json_malformed(mock_store, mock_llm):
    # LLM returns JSON with trailing comma
    response = MagicMock()
    response.content = '{"approved": true, "reason": "logic error", "confidence": 0.9,}'
    mock_llm.ainvoke.return_value = response

    screener = EvolutionScreener(store=mock_store, cheap_llm=mock_llm)
    request = EvolutionRequest(
        evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="Exception: division by zero"
    )

    result = await screener.screen_request(request)
    assert result.allowed is True
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_screener_intent_override(mock_store):
    # Even if recently evolved, force_retry should bypass cooldown
    screener = EvolutionScreener(store=mock_store, cooldown_seconds=3600)

    request = EvolutionRequest(
        evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="CustomError: error", force_retry=True
    )

    result = await screener.screen_request(request)
    # Depending on LLM presence, it goes to LLM phase or "none"
    # Here mock_llm is None, so it bypasses LLM
    assert result.allowed is True
    assert result.phase == "none"


def test_extract_signals_reads_status_exception_and_keywords():
    log = "HTTP 404 Not Found at url. Connection timeout during request. ValueError: invalid format."
    signals = extract_error_signals(log)

    assert "404" in signals.get("http_status", "")
    assert "ValueError" in signals.get("exception_types", "")
    assert "timeout" in signals.get("error_keywords", "")


def _llm_rejecting(confidence: float) -> AsyncMock:
    llm = AsyncMock()
    response = MagicMock()
    response.content = f'{{"approved": false, "reason": "not a skill defect", "confidence": {confidence}}}'
    llm.ainvoke.return_value = response
    return llm


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["balanced", "innovate"])
@pytest.mark.parametrize("evolution_type", list(EvolutionType))
async def test_balanced_and_innovate_let_every_evolution_type_through(mock_store, strategy, evolution_type):
    screener = EvolutionScreener(store=mock_store, evolution_strategy=strategy)

    result = await screener.screen_request(EvolutionRequest(evolution_type=evolution_type, skill_id="test_skill"))

    assert result.allowed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("evolution_type", [EvolutionType.DERIVED, EvolutionType.CAPTURED])
async def test_repair_only_blocks_everything_but_fix(mock_store, evolution_type):
    screener = EvolutionScreener(store=mock_store, evolution_strategy="repair-only")

    blocked = await screener.screen_request(EvolutionRequest(evolution_type=evolution_type, skill_id="test_skill"))
    fix = await screener.screen_request(EvolutionRequest(evolution_type=EvolutionType.FIX, skill_id="test_skill"))

    assert blocked.allowed is False
    assert blocked.phase == "strategy"
    assert fix.allowed is True


@pytest.mark.asyncio
async def test_innovate_overrides_a_rejection_the_confirmation_is_unsure_about(mock_store):
    request = EvolutionRequest(evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="HTTP 500: upstream")

    innovate = await EvolutionScreener(
        store=mock_store, cheap_llm=_llm_rejecting(0.5), evolution_strategy="innovate"
    ).screen_request(request)
    balanced = await EvolutionScreener(
        store=mock_store, cheap_llm=_llm_rejecting(0.5), evolution_strategy="balanced"
    ).screen_request(request)

    assert innovate.allowed is True
    assert "Innovate override" in innovate.reason
    assert balanced.allowed is False


@pytest.mark.asyncio
async def test_innovate_keeps_a_confident_rejection(mock_store):
    request = EvolutionRequest(evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="HTTP 500: upstream")
    screener = EvolutionScreener(store=mock_store, cheap_llm=_llm_rejecting(0.9), evolution_strategy="innovate")

    result = await screener.screen_request(request)

    assert result.allowed is False
    assert result.phase == "llm_confirmation"


def test_an_unknown_strategy_falls_back_to_balanced(mock_store):
    screener = EvolutionScreener(store=mock_store, evolution_strategy="innovate")

    screener.evolution_strategy = cast(EvolutionStrategy, "harden")

    assert screener.evolution_strategy == "balanced"


_FIX_REQUEST = EvolutionRequest(evolution_type=EvolutionType.FIX, skill_id="test_skill", reason="CustomError: boom")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored", "on_disk", "allowed"),
    [
        pytest.param(_UNLOCKED_MD, _LOCKED_MD, False, id="locked-in-the-file-only"),
        pytest.param(_LOCKED_MD, _UNLOCKED_MD, True, id="unlocked-in-the-file-after-the-store-copy-was-locked"),
        pytest.param(_LOCKED_MD, _LOCKED_MD, False, id="the-copy-and-the-file-agree-but-the-flag-is-behind"),
    ],
)
async def test_the_lock_in_the_skill_file_decides_not_the_one_in_the_store_copy(
    mock_store, write_skill_file, stored: str, on_disk: str, allowed: bool
) -> None:
    mock_store.get_skill.return_value = _skill_record(stored, write_skill_file(on_disk))

    result = await EvolutionScreener(store=mock_store).screen_request(_FIX_REQUEST)

    assert result.allowed is allowed
    if not allowed:
        assert result.phase == "locked"
        assert "SKILL.md" in result.reason


@pytest.mark.asyncio
async def test_the_confirmation_judges_the_text_of_the_file(mock_store, mock_llm, write_skill_file) -> None:
    mock_store.get_skill.return_value = _skill_record(_CODE, write_skill_file(_UNLOCKED_MD))

    await EvolutionScreener(store=mock_store, cheap_llm=mock_llm).screen_request(_FIX_REQUEST)

    prompt = mock_llm.ainvoke.await_args.args[0][0].content
    assert "Body as the file has it." in prompt
    assert _CODE not in prompt
