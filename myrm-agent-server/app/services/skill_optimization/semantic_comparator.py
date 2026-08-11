"""Semantic Comparator (Server Layer)

[INPUT]
- myrm_agent_harness.agent.skills.optimization.result_comparator::StructuredComparator (POS: 结构化比对器)
- app.core.utils.chat_utils::extract_litellm_answer_text (POS: litellm 响应文本提取)
- app.core.utils.chat_utils::parse_llm_json_object (POS: LLM judge JSON 容错解析)

[OUTPUT]
- compare_semantically: 结构化分数低于阈值时按需调用 LLM 判定语义等价

[POS]
Server 层的语义比对器，组合 Harness 层 StructuredComparator，仅在本地比对分数
低于阈值时按需调用 LLM 进行语义判定（实际 LLM 调用率预计 < 10%）。
"""

from __future__ import annotations

import json
import logging

from myrm_agent_harness.agent.skills.optimization.result_comparator import (
    ComparisonDetail,
    StructuredComparator,
)

from app.core.utils.chat_utils import (
    extract_litellm_answer_text,
    parse_llm_json_object,
)

logger = logging.getLogger(__name__)

_SEMANTIC_JUDGE_PROMPT = """You are a result comparator. Compare the BASELINE and CANDIDATE outputs of the same tool/skill call.

Your task: determine if they are semantically equivalent (same meaning, possibly different format/wording).

BASELINE:
{baseline}

CANDIDATE:
{candidate}

Respond with ONLY a JSON object:
{{"score": <float 0.0 to 1.0>, "reasoning": "<one sentence>"}}

score = 1.0 means semantically identical, 0.0 means completely different meaning.
Focus on the actual content/meaning, not formatting differences."""


class SemanticComparator:
    """语义比对器：本地比对 + 按需 LLM 语义判定

    委托 StructuredComparator 的 Layer1/2 能力，
    当 similarity_score 低于 semantic_threshold 时调用 LLM 进行 Layer3 语义判定。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        match_threshold: float = 0.85,
        llm_trigger_threshold: float = 0.7,
        structural_weight: float = 0.3,
        textual_weight: float = 0.3,
        semantic_weight: float = 0.4,
        llm_timeout: float = 15.0,
    ) -> None:
        self._structured = StructuredComparator(
            match_threshold=match_threshold,
            structural_weight=0.4,
            textual_weight=0.6,
        )
        self.match_threshold = match_threshold
        self.model = model
        self._llm_trigger_threshold = llm_trigger_threshold
        self._s_weight = structural_weight
        self._t_weight = textual_weight
        self._sem_weight = semantic_weight
        self.llm_timeout = llm_timeout

    async def compare(
        self,
        baseline: dict[str, object],
        candidate: dict[str, object],
    ) -> ComparisonDetail:
        base_result = await self._structured.compare(baseline, candidate)

        if base_result.is_match:
            return base_result

        local_avg = (base_result.structural_score + base_result.textual_score) / 2.0

        if local_avg < 0.1:
            return base_result

        if local_avg >= self._llm_trigger_threshold:
            return base_result

        semantic_score = await self._llm_semantic_judge(baseline, candidate)

        if semantic_score is not None:
            combined = (
                self._s_weight * base_result.structural_score
                + self._t_weight * base_result.textual_score
                + self._sem_weight * semantic_score
            )
            combined = max(0.0, min(1.0, combined))

            return ComparisonDetail(
                similarity_score=combined,
                is_match=combined >= self.match_threshold,
                structural_score=base_result.structural_score,
                textual_score=base_result.textual_score,
                diff_summary=f"{base_result.diff_summary}; LLM semantic: {semantic_score:.0%}",
                field_diffs=base_result.field_diffs,
            )

        return base_result

    async def _llm_semantic_judge(
        self,
        baseline: dict[str, object],
        candidate: dict[str, object],
    ) -> float | None:
        """调用 LLM 进行语义相似度判定"""
        try:
            import litellm

            b_str = json.dumps(baseline, ensure_ascii=False, default=str)[:2000]
            c_str = json.dumps(candidate, ensure_ascii=False, default=str)[:2000]

            prompt = _SEMANTIC_JUDGE_PROMPT.format(baseline=b_str, candidate=c_str)

            response = await litellm.acompletion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                timeout=self.llm_timeout,
                temperature=0.0,
                # Reasoning models burn tokens on chain-of-thought; keep headroom
                # so the final JSON object is not truncated mid-string.
                max_tokens=600,
            )

            # 兼容 Anthropic 块列表 / reasoning 模型 content 空回退
            content = extract_litellm_answer_text(response).strip()

            parsed_obj = parse_llm_json_object(content)
            if parsed_obj is None:
                logger.warning("LLM semantic judge returned no parseable JSON")
                return None
            parsed = parsed_obj
            score_raw = parsed.get("score", 0.5)
            if isinstance(score_raw, bool) or not isinstance(
                score_raw, int | float | str
            ):
                score = 0.5
            else:
                score = float(score_raw)
            score = max(0.0, min(1.0, score))

            logger.info(
                f"LLM semantic judge: score={score:.2f}, reasoning={parsed.get('reasoning', 'N/A')}"
            )
            return score

        except Exception as e:
            logger.warning(f"LLM semantic judge failed, falling back to local: {e}")
            return None
