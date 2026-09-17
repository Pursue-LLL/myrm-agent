"""Memory command center economics analytics service.

[INPUT]
app.database.models.chat::Message (POS: 会话消息 ORM 实体)
app.schemas.memory.command_center::MemoryCommandInfluenceItem (POS: 记忆影响力与引用状态契约)
myrm_agent_harness.toolkits.memory.observability::MemoryPhaseLatency (POS: Harness 业务中立的三阶段开销指标模型)

[OUTPUT]
MemoryCommandEconomicsDashboard: Long-horizon memory cost, Omri 2026 three-phase latency,
ROI grade, turn-by-turn trajectory, and parasitic memory identification.

[POS]
长程任务记忆经济学分析服务。对标 Omri et al. (2026)，拆解构建/检索/注入三阶段开销，
量化长程任务有效召回 ROI 与 Prompt Cache 保持率，识别沉睡低效记忆池并联动 Doctor 治理。
"""

from __future__ import annotations

import logging
import re
from typing import Mapping, Sequence

from myrm_agent_harness.toolkits.memory import (
    MemoryRecallRoiGrade,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.chat import Message
from app.schemas.memory.command_center import (
    MemoryCommandCostProfile,
    MemoryCommandEconomicsDashboard,
    MemoryCommandInfluenceItem,
    MemoryCommandParasiticMemory,
    MemoryCommandTurnEconomics,
)

logger = logging.getLogger(__name__)

# Heuristic token weight: CJK character ~ 1.5 tokens, Latin words ~ 1.3 tokens
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_WORD_PATTERN = re.compile(r"\b\w+\b")
_PUNCT_PATTERN = re.compile(r"[^\w\s]")


def estimate_memory_tokens_safe(content: str) -> int:
    """Accurate token estimator handling CJK, code symbols, and words without split() flaws."""
    if not content:
        return 0
    cjk_count = len(_CJK_PATTERN.findall(content))
    ascii_only = _CJK_PATTERN.sub(" ", content)
    words = len(_WORD_PATTERN.findall(ascii_only))
    punct_count = len(_PUNCT_PATTERN.findall(ascii_only))
    # Base estimate: CJK ~ 1.3 tokens/char, words ~ 1.3 tokens/word, punctuation/symbols ~ 0.5 tokens
    token_est = int(cjk_count * 1.3 + words * 1.3 + punct_count * 0.5)
    return max(1, token_est)


def classify_roi_grade(roi_percentage: float) -> str:
    """Classify ROI percentage into standardized grades."""
    if roi_percentage >= 50.0:
        return MemoryRecallRoiGrade.OPTIMAL.value
    if roi_percentage >= 25.0:
        return MemoryRecallRoiGrade.HEALTHY.value
    if roi_percentage >= 10.0:
        return MemoryRecallRoiGrade.DILUTED.value
    return MemoryRecallRoiGrade.CRITICAL.value


class MemoryEconomicsService:
    """Evaluates memory economics for long-horizon sessions and command center dashboard."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build_economics_dashboard(
        self,
        *,
        influence: Sequence[MemoryCommandInfluenceItem],
        session_id: str | None = None,
        pinned_memory_ids: Sequence[str] | None = None,
        archived_memory_ids: Sequence[str] | set[str] | None = None,
        memory_previews: Mapping[str, tuple[str, str]] | None = None,
        limit_turns: int = 50,
    ) -> MemoryCommandEconomicsDashboard:
        """Construct a comprehensive long-horizon memory economics dashboard."""
        query = select(Message).where(Message.extra_data.is_not(None))
        if session_id:
            query = query.where(Message.chat_id == session_id)

        query = query.order_by(desc(Message.created_at)).limit(limit_turns)

        result = await self._db.execute(query)
        messages = list(reversed(result.scalars().all()))

        all_pinned_ids: set[str] = set(pinned_memory_ids or [])
        all_archived_ids: set[str] = set(archived_memory_ids or [])
        turn_trajectories: list[MemoryCommandTurnEconomics] = []
        injected_counter: dict[str, int] = {}
        cited_counter: dict[str, int] = {}
        preview_map: dict[str, str] = {}
        type_map: dict[str, str] = {}

        if memory_previews:
            for m_id, (prev, m_type) in memory_previews.items():
                if m_id:
                    preview_map.setdefault(m_id, prev)
                    type_map.setdefault(m_id, m_type)

        if influence:
            for item in influence:
                for ref in item.influence_refs:
                    if ref.memory_id:
                        preview_map.setdefault(ref.memory_id, ref.content_preview)
                        type_map.setdefault(ref.memory_id, ref.memory_type)

        total_prompt_tokens = 0
        total_cached_tokens = 0
        total_completion_tokens = 0
        total_injected_memory_tokens = 0
        total_cited_tokens = 0
        total_cited_refs = 0
        total_retrieval_ms = 0.0
        total_construction_ms = 0.0
        total_injection_ms = 0.0

        for turn_idx, msg in enumerate(messages):
            extra: Mapping[str, object] = msg.extra_data or {}
            usage = self._extract_token_counts(extra)
            prompt_tok, cached_tok, comp_tok = usage
            total_prompt_tokens += prompt_tok
            total_cached_tokens += cached_tok
            total_completion_tokens += comp_tok

            # Memory references and telemetry from extra_data
            mem_meta = self._extract_memory_metadata(extra)
            injected_tok = mem_meta.get("injected_memory_tokens", 0)
            retrieval_ms = mem_meta.get("retrieval_ms", 12.0)
            construction_ms = mem_meta.get("construction_ms", 0.0)
            injection_ms = float(mem_meta.get("injection_overhead_ms") or 1.5)
            cache_aligned = mem_meta.get("cache_aligned", True)

            total_retrieval_ms += retrieval_ms
            total_construction_ms += construction_ms
            total_injection_ms += injection_ms

            # Cited memory tracking
            cited_refs = self._extract_cited_refs(extra)
            turn_cited_tokens = 0
            for ref_id, preview, mtype in cited_refs:
                cited_counter[ref_id] = cited_counter.get(ref_id, 0) + 1
                preview_map[ref_id] = preview
                type_map[ref_id] = mtype
                turn_cited_tokens += estimate_memory_tokens_safe(preview)

            # Injected memory tracking, pinned memory detection & archived memory extraction
            injected_ids, turn_pinned_ids = self._extract_injected_ids_and_pins(
                extra, preview_map=preview_map, type_map=type_map
            )
            all_pinned_ids.update(turn_pinned_ids)
            all_archived_ids.update(self._extract_archived_ids(extra))
            for m_id in injected_ids:
                injected_counter[m_id] = injected_counter.get(m_id, 0) + 1

            total_injected_memory_tokens += injected_tok
            total_cited_tokens += turn_cited_tokens
            total_cited_refs += len(cited_refs)

            turn_roi = (
                (turn_cited_tokens / max(injected_tok, 1)) * 100.0 if injected_tok > 0 else 100.0
            )
            turn_trajectories.append(
                MemoryCommandTurnEconomics(
                    turn_index=turn_idx + 1,
                    message_id=str(msg.id),
                    injected_tokens=injected_tok,
                    cited_tokens=turn_cited_tokens,
                    cached_tokens=cached_tok,
                    roi_percentage=round(min(100.0, turn_roi), 1),
                    cache_aligned=cache_aligned,
                    retrieval_ms=round(retrieval_ms, 1),
                )
            )

        # Baseline fallback with current influence items if messages metadata is sparse
        if total_injected_memory_tokens == 0 and influence:
            for item in influence:
                for ref in item.influence_refs:
                    tok = estimate_memory_tokens_safe(ref.content_preview)
                    total_injected_memory_tokens += tok
                    total_cited_tokens += tok
                    cited_counter[ref.memory_id] = cited_counter.get(ref.memory_id, 0) + 1
                    preview_map[ref.memory_id] = ref.content_preview
                    type_map[ref.memory_id] = ref.memory_type

        # Compute overall ROI and cache preservation score
        denominator = max(total_injected_memory_tokens, 1)
        roi_pct = round((total_cited_tokens / denominator) * 100.0, 1)
        cache_score = (
            round(total_cached_tokens / max(total_prompt_tokens, 1), 2)
            if total_prompt_tokens > 0
            else 1.0
        )
        roi_grade = classify_roi_grade(roi_pct)

        # Identify parasitic memories (injected >= 3 times but cited 0 times)
        # Core user profile, identity facts, pinned memories, and already archived memories enjoy permanent exemption
        exempt_memory_types = {"profile", "user_profile", "identity", "core_fact"}
        parasitic_memories: list[MemoryCommandParasiticMemory] = []
        for mem_id, in_count in injected_counter.items():
            if mem_id in all_pinned_ids or mem_id in all_archived_ids:
                continue
            mtype = type_map.get(mem_id, "semantic")
            if mtype in exempt_memory_types:
                continue
            c_count = cited_counter.get(mem_id, 0)
            if in_count >= 3 and c_count == 0:
                prev = preview_map.get(mem_id, f"Memory item {mem_id}")
                wasted = estimate_memory_tokens_safe(prev) * in_count
                parasitic_memories.append(
                    MemoryCommandParasiticMemory(
                        memory_id=mem_id,
                        memory_type=mtype,
                        content_preview=prev[:100],
                        injected_turns_count=in_count,
                        cited_turns_count=0,
                        wasted_tokens_estimated=wasted,
                        suggested_action="archive",
                    )
                )

        # Sort parasitic candidates by wasted tokens descending
        parasitic_memories.sort(key=lambda x: x.wasted_tokens_estimated, reverse=True)

        # Estimate potential financial savings based on model rate
        rate_per_1m = 3.0
        if messages:
            m_name = str((messages[-1].extra_data or {}).get("model") or "").lower()
            if "deepseek" in m_name:
                rate_per_1m = 0.28
            elif "mini" in m_name or "flash" in m_name:
                rate_per_1m = 0.30
        total_wasted_tokens = sum(p.wasted_tokens_estimated for p in parasitic_memories)
        est_savings_usd = round((total_wasted_tokens / 1_000_000.0) * rate_per_1m, 4)

        recommendations: list[str] = []
        if cache_score < 0.6:
            recommendations.append("提示词前缀缓存保持率较低，建议将记忆注入锚点固定在系统指令后方以保护缓存。")
        if parasitic_memories:
            recommendations.append(
                f"发现 {len(parasitic_memories)} 条长期未被引用的沉睡记忆，建议通过 Memory Doctor 进行一键归档。"
            )
        if roi_pct < 20.0 and total_injected_memory_tokens > 1000:
            recommendations.append("记忆召回利用率偏低，建议适当缩紧检索相似度阈值或降低装载预算。")
        if not recommendations:
            recommendations.append("记忆系统经济学表现优异，三阶段开销与提示词前缀缓存保持健康。")

        avg_retrieval_ms = total_retrieval_ms / max(len(messages), 1)
        avg_construction_ms = total_construction_ms / max(len(messages), 1)
        avg_injection_ms = total_injection_ms / max(len(messages), 1)

        cost_profile = MemoryCommandCostProfile(
            prompt_tokens=total_prompt_tokens,
            cached_tokens=total_cached_tokens,
            completion_tokens=total_completion_tokens,
            cited_memory_refs=total_cited_refs,
            estimated_memory_tokens=total_injected_memory_tokens,
            cache_friendly=cache_score >= 0.5,
            construction_ms=round(avg_construction_ms, 1),
            retrieval_ms=round(avg_retrieval_ms, 1),
            injection_overhead_ms=round(avg_injection_ms, 1),
            effective_cited_tokens=total_cited_tokens,
            background_construction_tokens=int(total_completion_tokens * 0.1),
            cache_preservation_score=cache_score,
            roi_percentage=roi_pct,
            roi_grade=roi_grade,
            parasitic_memory_count=len(parasitic_memories),
        )

        return MemoryCommandEconomicsDashboard(
            cost_profile=cost_profile,
            turn_trajectories=turn_trajectories,
            parasitic_memories=parasitic_memories,
            estimated_cost_savings_usd=est_savings_usd,
            recommendations=recommendations,
        )

    @staticmethod
    def _extract_token_counts(extra_data: Mapping[str, object]) -> tuple[int, int, int]:
        """Safely extract prompt, cached, and completion tokens from message extra_data."""
        usage = extra_data.get("usage")
        if not isinstance(usage, dict):
            return 0, 0, 0
        prompt = int(usage.get("prompt_tokens") or 0)
        cached = int(
            usage.get("cached_tokens")
            or usage.get("prompt_cache_hit_tokens")
            or usage.get("cache_read_input_tokens")
            or 0
        )
        return prompt, cached, int(usage.get("completion_tokens") or 0)

    @staticmethod
    def _extract_memory_metadata(extra_data: Mapping[str, object]) -> dict[str, object]:
        """Extract memory phase latency and injection metadata."""
        meta = extra_data.get("memory_telemetry")
        return dict(meta) if isinstance(meta, dict) else {}

    @staticmethod
    def _extract_cited_refs(
        extra_data: Mapping[str, object],
    ) -> list[tuple[str, str, str]]:
        """Extract list of cited (memory_id, content_preview, memory_type) from message."""
        citations = extra_data.get("citations") or extra_data.get("memory_citations") or []
        results: list[tuple[str, str, str]] = []
        if isinstance(citations, list):
            for cite in citations:
                if isinstance(cite, dict):
                    m_id = str(cite.get("id") or cite.get("memory_id") or "")
                    preview = str(cite.get("content") or cite.get("preview") or "")
                    m_type = str(cite.get("type") or "semantic")
                    if m_id:
                        results.append((m_id, preview, m_type))
        return results

    @staticmethod
    def _extract_injected_ids_and_pins(
        extra_data: Mapping[str, object],
        preview_map: dict[str, str] | None = None,
        type_map: dict[str, str] | None = None,
    ) -> tuple[list[str], set[str]]:
        """Extract injected memory IDs and pinned memory IDs from message metadata."""
        injected_ids: list[str] = []
        pinned_ids: set[str] = set()

        raw_injected = extra_data.get("injected_memory_ids") or extra_data.get("injected_memories") or []
        for item in raw_injected if isinstance(raw_injected, list) else []:
            if isinstance(item, str) and item:
                injected_ids.append(item)
            elif isinstance(item, dict):
                m_id = str(item.get("id") or item.get("memory_id") or "")
                if m_id:
                    injected_ids.append(m_id)
                    if item.get("pinned") is True or item.get("is_pinned") is True:
                        pinned_ids.add(m_id)
                    if preview_map is not None:
                        cnt = item.get("content") or item.get("preview") or item.get("text")
                        if cnt:
                            preview_map.setdefault(m_id, str(cnt))
                    if type_map is not None:
                        mt = item.get("memory_type") or item.get("type")
                        if mt:
                            type_map.setdefault(m_id, str(mt))

        raw_pinned = extra_data.get("pinned_memory_ids") or extra_data.get("pinned_memories") or []
        for p_item in raw_pinned if isinstance(raw_pinned, list) else []:
            if isinstance(p_item, str) and p_item:
                pinned_ids.add(p_item)
            elif isinstance(p_item, dict):
                p_id = str(p_item.get("id") or p_item.get("memory_id") or "")
                if p_id:
                    pinned_ids.add(p_id)

        telemetry = extra_data.get("memory_telemetry")
        if isinstance(telemetry, dict):
            for tp in telemetry.get("pinned_memory_ids") or []:
                if isinstance(tp, str) and tp:
                    pinned_ids.add(tp)

        return injected_ids, pinned_ids

    @staticmethod
    def _extract_archived_ids(extra_data: Mapping[str, object]) -> set[str]:
        """Extract archived or forgotten memory IDs from message metadata."""
        archived_ids: set[str] = set()
        raw = (
            extra_data.get("archived_memory_ids")
            or extra_data.get("archived_memories")
            or extra_data.get("forgotten_memory_ids")
            or []
        )
        for a_item in raw if isinstance(raw, list) else []:
            if isinstance(a_item, str) and a_item:
                archived_ids.add(a_item)
            elif isinstance(a_item, dict):
                a_id = str(a_item.get("id") or a_item.get("memory_id") or "")
                if a_id:
                    archived_ids.add(a_id)

        telemetry = extra_data.get("memory_telemetry")
        if isinstance(telemetry, dict):
            for ta in telemetry.get("archived_memory_ids") or []:
                if isinstance(ta, str) and ta:
                    archived_ids.add(ta)

        return archived_ids
