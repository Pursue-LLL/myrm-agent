"""结构化摘要生成、预算提示与结果裁剪。

[POS]
摘要策略子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import time

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage

from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.audit import (
    _record_summarize_to_metrics,
    _summarize_full_with_audit,
    _summarize_incremental_with_audit,
)
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.budget import (
    _cap_summary_if_needed,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.token_estimation import (
    estimate_messages_tokens,
)

from ....infra.schemas import ContextConfig, StructuredSummary
from ..progress_timeout import (
    SummaryProgressTracker,
)
from ..summary_builder import (
    TailExtractionResult,
    create_summary_message,
    extract_recent_messages_with_split_context,
)
from ..summary_parser import (
    extract_existing_summary,
    extract_messages_after_summary,
)

logger = get_agent_logger(__name__)


async def generate_structured_summary(
    messages: list[BaseMessage],
    llm: BaseChatModel,
    chat_id: str | None = None,
    existing_summary: StructuredSummary | None = None,
    config: ContextConfig | None = None,
    focus_topic: str = "",
    pre_compact_message: BaseMessage | None = None,
    progress_tracker: SummaryProgressTracker | None = None,
) -> tuple[list[BaseMessage], StructuredSummary]:
    """Generate structured summary and rebuild message list (pure in-memory).

    Two modes:
    1. Full: generate a complete new summary
    2. Incremental: merge new content into an existing summary
    """
    _summarize_start = time.monotonic()

    from ....infra.schemas import DEFAULT_CONTEXT_CONFIG

    cfg = config or DEFAULT_CONTEXT_CONFIG

    if existing_summary is None:
        existing_summary = extract_existing_summary(messages)

    is_incremental = existing_summary is not None
    mode_str = "incremental" if is_incremental else "full"
    logger.warning(" Starting context summary (%s)...", mode_str)

    dump_path = ""

    tail_budget = int((cfg.max_context_tokens or 128000) * getattr(cfg, "tail_budget_ratio", 0.20))
    tail_result: TailExtractionResult = extract_recent_messages_with_split_context(messages, tail_budget)
    recent_messages = list(tail_result.messages)
    original_tokens = estimate_messages_tokens(messages)

    from ..exact_anchor import extract_exact_anchors
    from ..summary_auditor import extract_key_entities

    entities = extract_key_entities(messages)
    exact_anchors = extract_exact_anchors(messages)

    turn_prefix_messages = tail_result.turn_prefix_messages if tail_result.is_split_turn else None

    if is_incremental and existing_summary is not None:
        new_messages_only = extract_messages_after_summary(messages)
        if new_messages_only:
            summary = await _summarize_incremental_with_audit(
                llm,
                existing_summary,
                new_messages_only,
                dump_path,
                messages,
                entities,
                focus_topic=focus_topic,
                turn_prefix_messages=turn_prefix_messages,
                progress_tracker=progress_tracker,
                chat_id=chat_id,
                exact_anchors=exact_anchors,
            )
        else:
            summary = existing_summary
            summary.context_dump_path = dump_path
            logger.warning(" No new content, keeping existing summary")
    else:
        summary = await _summarize_full_with_audit(
            llm,
            messages,
            dump_path,
            entities,
            focus_topic=focus_topic,
            turn_prefix_messages=turn_prefix_messages,
            progress_tracker=progress_tracker,
            chat_id=chat_id,
            exact_anchors=exact_anchors,
        )

    # Physical execution state reconciliation (Auto-Reconcile with ArtifactTracker)
    from ..execution_state_validator import reconcile_summary_execution_state

    summary = reconcile_summary_execution_state(summary, chat_id, messages)

    # Branch-scoped subagent compaction merge (enrich summary with child outcomes)
    if chat_id:
        try:
            from myrm_agent_harness.agent.sub_agents.branch_scoped_compaction import (
                merge_subagent_handovers_into_summary,
            )

            summary = merge_subagent_handovers_into_summary(summary, chat_id)
        except Exception as e:
            logger.debug("[Summarize] Failed to merge subagent branch handovers: %s", e)

    import hashlib
    import re

    from ..summary_builder import extract_protected_head

    protected_head = extract_protected_head(messages)

    # Prevent overlap between protected_head and recent_messages
    protected_ids = {id(m) for m in protected_head}
    recent_messages = [m for m in recent_messages if id(m) not in protected_ids]

    # Dropped-constraint audit: record user constraints evicted by this
    # compaction (redacted + truncated) so the GUI can distinguish "compression
    # dropped my instruction" from "the model failed to follow it". Pure local
    # computation — never enters to_json()/prompts.
    from ..dropped_manifest import build_dropped_manifest

    summary.dropped_manifest = build_dropped_manifest(
        messages,
        protected_ids=protected_ids,
        recent_ids={id(m) for m in recent_messages},
    )
    if summary.dropped_manifest:
        logger.warning(
            " Summary dropped %d user constraint snippet(s) from context: %s",
            len(summary.dropped_manifest),
            summary.dropped_manifest,
        )

    # Remove old preserved context messages to prevent accumulation
    protected_head = [
        msg
        for msg in protected_head
        if not (isinstance(msg, SystemMessage) and str(msg.content).startswith("[SYSTEM: PRESERVED CONTEXT]"))
    ]

    # --- Generic Context Preservation Logic ---
    # Extracts <preserve_context> tags from any message, deduplicates them,
    # truncates them to prevent OOM, and embeds them inside the summary HumanMessage
    # to protect the system prompt prefix cache from invalidation.
    rescued_context_blocks = {}
    preserve_tag_pattern = re.compile(r"<preserve_context>(.*?)</preserve_context>", re.DOTALL | re.IGNORECASE)
    max_preserve_chars = 2000

    from ....eviction_marks.marks import is_eviction_immune

    for msg in messages:
        content_str = str(msg.content)
        matches = preserve_tag_pattern.findall(content_str)
        for match in matches:
            clean_match = match.strip()
            if not clean_match:
                continue

            if len(clean_match) > max_preserve_chars:
                clean_match = clean_match[:max_preserve_chars] + "\n...[TRUNCATED]"

            block_hash = hashlib.md5(clean_match.encode("utf-8")).hexdigest()
            if block_hash not in rescued_context_blocks:
                # Re-wrap in tags so it survives multiple summarizations
                rescued_context_blocks[block_hash] = f"<preserve_context>\n{clean_match}\n</preserve_context>"

        if is_eviction_immune(msg):
            clean_val = content_str.strip()
            if clean_val:
                if len(clean_val) > max_preserve_chars:
                    clean_val = clean_val[:max_preserve_chars] + "\n...[TRUNCATED]"
                block_hash = hashlib.md5(clean_val.encode("utf-8")).hexdigest()
                if block_hash not in rescued_context_blocks:
                    rescued_context_blocks[block_hash] = (
                        f"<preserve_context>\n[IMMUNE RULE / EVICTION MARK]\n{clean_val}\n</preserve_context>"
                    )

    # Inject verified exact anchor index into preserved context
    anchor_md = exact_anchors.format_markdown()
    if anchor_md:
        anchor_hash = hashlib.md5(anchor_md.encode("utf-8")).hexdigest()
        rescued_context_blocks[anchor_hash] = f"<preserve_context>\n{anchor_md}\n</preserve_context>"

    combined_preserved = None
    if rescued_context_blocks:
        combined_preserved = "\n\n".join(rescued_context_blocks.values())

    summary = _cap_summary_if_needed(
        summary,
        original_tokens,
        recent_messages,
        chat_id,
        preserved_context=combined_preserved,
    )

    # Preserved context is embedded in summary HumanMessage (not SystemMessage)
    # to protect the system prompt prefix cache from invalidation.
    summary_message = create_summary_message(summary, chat_id, preserved_context=combined_preserved)
    middle_messages: list[BaseMessage] = [summary_message]
    if pre_compact_message is not None:
        middle_messages = [pre_compact_message, summary_message]

    new_messages = protected_head + middle_messages + recent_messages

    new_tokens = estimate_messages_tokens(new_messages)
    saved_tokens = original_tokens - new_tokens

    logger.warning(
        " Summary done: %d -> %d tokens (saved %d)",
        original_tokens,
        new_tokens,
        saved_tokens,
    )

    mode_detail = "incremental" if is_incremental else "full"
    _elapsed_ms = int((time.monotonic() - _summarize_start) * 1000)
    _record_summarize_to_metrics(
        saved_tokens,
        f"Summarized {len(messages)} messages ({mode_detail})",
        elapsed_ms=_elapsed_ms,
    )

    return new_messages, summary


# ---------------------------------------------------------------------------
# Summary budget calculation
# ---------------------------------------------------------------------------

