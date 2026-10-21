"""Locomo v2 adapter — Long-term conversational memory benchmark for Eval Lab.

[INPUT]
- json: Parse offline fixtures or remote benchmark dumps
- myrm_agent_harness.eval::BenchmarkSpec, register_benchmark
- myrm_agent_harness.eval::MultiTurnEvalCase, EvalCase, SemanticAssertion

[OUTPUT]
- list_locomo_source(): catalog entry with local availability
- ensure_locomo_source(): verify or initialize dataset fixtures
- build_locomo_cases(): construct runnable MultiTurnEvalCases

[POS]
Server-layer adapter that bridges the Locomo v2 long-term memory benchmark
into Eval Lab. Built-in with an offline zero-network smoke fixture
(`locomo_smoke.json`) providing instant evaluations for developer loops,
and supports full benchmark JSON datasets when configured.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.eval import (
    BenchmarkSpec,
    EvalCase,
    MultiTurnEvalCase,
    SemanticAssertion,
    register_benchmark,
)

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
LOCOMO_SMOKE_PATH = FIXTURES_DIR / "locomo_smoke.json"
LOCOMO_CUSTOM_PATH = Path(".myrm/locomo/locomo_dataset.json")

LOCOMO_JUDGE_PROMPT = """You are an objective judge evaluating whether an AI assistant accurately retained and applied long-term conversational memory facts across multiple turns.

{criteria}

Assistant Output:
{output}

Judge strictly by semantic agreement with the ground truth and evaluation rubric.
The assistant output is CORRECT when it satisfies the rubric, accurately reflects remembered facts, and does not contradict prior user instructions or corrections.
Reply EXACTLY with 'PASS' if correct, or 'FAIL: <reason>' if incorrect."""


def _get_dataset_path() -> Path:
    """Return custom dataset if present on disk, otherwise default to built-in smoke fixture."""
    if LOCOMO_CUSTOM_PATH.exists() and LOCOMO_CUSTOM_PATH.stat().st_size > 0:
        return LOCOMO_CUSTOM_PATH
    return LOCOMO_SMOKE_PATH


def list_locomo_source() -> dict[str, object]:
    """Catalog entry for Locomo v2 benchmark source."""
    path = _get_dataset_path()
    is_available = path.exists()
    count = 0
    size_bytes = 0
    if is_available:
        try:
            size_bytes = path.stat().st_size
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    count = len(data)
        except Exception:
            logger.debug("Failed to read task count from %s", path)

    return {
        "is_available": is_available,
        "task_count": count or 10,
        "local_size_bytes": size_bytes,
        "approx_size_mb": 0.1,
        "supports_memory_ab": True,
        "source_path": str(path),
    }


async def ensure_locomo_source(
    *,
    on_progress: Callable[[float, str], None] | None = None,
    abort_check: Callable[[], bool] | None = None,
) -> Path:
    """Ensure Locomo dataset is available locally."""
    if abort_check and abort_check():
        raise RuntimeError("Locomo download aborted")

    if on_progress:
        on_progress(0.5, "Verifying Locomo memory benchmark fixtures...")

    path = _get_dataset_path()
    if not path.exists():
        raise FileNotFoundError(f"Locomo dataset fixture not found at {path}")

    if on_progress:
        on_progress(1.0, "Locomo memory benchmark ready")

    return path


def build_locomo_cases(
    limit: int = 0,
    sample_seed: int = 42,
) -> tuple[list[MultiTurnEvalCase], dict[str, int], bool]:
    """Build runnable MultiTurnEvalCase instances from Locomo dataset.

    Returns:
        tuple of (cases, seed_map, is_sampled)
    """
    path = _get_dataset_path()
    if not path.exists():
        logger.warning("Locomo dataset path %s not found", path)
        return [], {}, False

    try:
        with path.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        logger.error("Failed to parse Locomo dataset from %s: %s", path, e)
        return [], {}, False

    if not isinstance(raw_data, list):
        return [], {}, False

    items = list(raw_data)
    total_count = len(items)
    is_sampled = False

    if 0 < limit < total_count:
        import random

        rng = random.Random(sample_seed)
        items = rng.sample(items, limit)
        is_sampled = True

    cases: list[MultiTurnEvalCase] = []
    seed_map: dict[str, int] = {}

    for idx, item in enumerate(items):
        case_id = str(item.get("id") or f"locomo-{idx + 1:03d}")
        seed_map[case_id] = sample_seed + idx

        turns_raw = item.get("turns", [])
        ground_truth = str(item.get("ground_truth", ""))
        rubric = str(item.get("rubric", ""))

        sub_cases: list[EvalCase] = []
        for t_idx, turn in enumerate(turns_raw):
            is_final_turn = t_idx == len(turns_raw) - 1
            user_input = str(turn.get("user_input", ""))
            assertions: list[SemanticAssertion] = []
            if is_final_turn:
                criteria = (
                    f"Ground Truth Reference:\n{ground_truth}\n\n"
                    f"Evaluation Rubric:\n{rubric}"
                )
                assertions.append(
                    SemanticAssertion(
                        type="llm_judge",
                        expected=criteria,
                        threshold=1.0,
                        judge_prompt=LOCOMO_JUDGE_PROMPT,
                    )
                )

            metadata = {
                "case_id": case_id,
                "turn_index": str(t_idx + 1),
                "total_turns": str(len(turns_raw)),
            }
            if turn.get("expected_response_substring"):
                metadata["expected_response_substring"] = str(turn["expected_response_substring"])

            sub_cases.append(
                EvalCase(
                    message=user_input,
                    semantic_assertions=assertions,
                    metadata=metadata,
                )
            )

        cases.append(
            MultiTurnEvalCase(
                turns=sub_cases,
                metadata={
                    "id": case_id,
                    "name": str(item.get("name") or case_id),
                    "category": str(item.get("category") or "memory"),
                    "benchmark_source": "locomo",
                },
            )
        )

    return cases, seed_map, is_sampled


LOCOMO_SPEC = BenchmarkSpec(
    id="locomo",
    display_name="Locomo v2 (Long-term Memory Benchmark)",
    description=(
        "Long-term conversational memory benchmark assessing retention, temporal correction, "
        "and constraint recall across multi-turn dialogs."
    ),
    download_url="",
    task_count=10,
    approx_size_mb=0.1,
    scoring="llm_judge",
    required_tools=(),
    supports_memory_ab=True,
    max_tool_calls=20,
    max_iterations=30,
    harness="myrm",
)

# Self-register spec with framework registry on import
register_benchmark(LOCOMO_SPEC)
