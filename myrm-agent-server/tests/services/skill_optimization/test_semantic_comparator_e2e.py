"""Real-LLM e2e tests for SemanticComparator's LLM semantic-judge path.

The judge route feeds a real ``litellm.acompletion`` response through
``extract_litellm_answer_text`` (the reasoning-model-aware extractor fixed in
this task). No mocks on the LLM path.
"""

from __future__ import annotations

import os

import pytest

from app.services.skill_optimization.semantic_comparator import SemanticComparator

pytestmark = pytest.mark.e2e


def _bridge_lite_env_to_minimax() -> None:
    """SemanticComparator calls litellm.acompletion(model='minimax/...') directly.

    litellm resolves credentials from MINIMAX_API_KEY / MINIMAX_API_BASE; bridge
    them from the LITE_* test lane keys without mutating .env.test.
    """
    api_key = os.environ.get("LITE_API_KEY")
    api_base = os.environ.get("LITE_BASE_URL")
    model = os.environ.get("LITE_MODEL", "")
    if not (api_key and api_base and model.startswith("minimax/")):
        pytest.skip("LITE minimax lane not configured — real-LLM judge cannot run")
    os.environ.setdefault("MINIMAX_API_KEY", api_key)
    os.environ.setdefault("MINIMAX_API_BASE", api_base)


@pytest.mark.asyncio
async def test_semantic_judge_llm_triggered_real_llm() -> None:
    """local_avg in [0.1, 0.7) triggers the real-LLM judge; result is a sane score."""
    _bridge_lite_env_to_minimax()
    model = os.environ["LITE_MODEL"]

    comp = SemanticComparator(
        model=model,
        match_threshold=0.85,
        llm_trigger_threshold=0.7,
        llm_timeout=30.0,
    )
    baseline = {
        "status": "ok",
        "result": "the quick brown fox jumps over the lazy dog",
    }
    candidate = {
        "status": "ok",
        "result": "the quick brown fox leaps over the lazy dog",
    }

    detail = await comp.compare(baseline, candidate)

    assert "LLM semantic" in detail.diff_summary, "LLM semantic judge must run and annotate the diff summary"
    assert 0.0 <= detail.similarity_score <= 1.0
    assert isinstance(detail.is_match, bool)
