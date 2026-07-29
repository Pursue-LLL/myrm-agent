"""Consolidation insight → wiki raw bridge.

[INPUT]
myrm_agent_harness.toolkits.memory.strategies.consolidation::ConsolidationStats (POS: consolidation result)
myrm_agent_harness.toolkits.wiki.pipeline.raw_gate::publish_raw (POS: raw publication gate)

[OUTPUT]
make_consolidation_wiki_bridge / archive_consolidation_insights_to_wiki

[POS]
Server hook: when Memory consolidation yields insights (enable_wiki gate is upstream),
writes a digest markdown under wiki/raw/memory/ and enqueues compile.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.toolkits.memory.strategies.consolidation import ConsolidationStats
from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
    RawConflictPolicy,
    RawPublishRequest,
    publish_raw,
)

logger = logging.getLogger(__name__)


def make_consolidation_wiki_bridge(
    *,
    agent_id: str | None,
    llm: BaseChatModel,
) -> Callable[[ConsolidationStats], Awaitable[None]]:
    """Return a consolidation-complete hook that archives insights into wiki/raw."""

    async def _bridge(stats: ConsolidationStats) -> None:
        await archive_consolidation_insights_to_wiki(stats, agent_id=agent_id, llm=llm)

    return _bridge


async def archive_consolidation_insights_to_wiki(
    stats: ConsolidationStats,
    *,
    agent_id: str | None,
    llm: BaseChatModel,
) -> None:
    """Write consolidation insights to wiki/raw (caller must gate on enable_wiki)."""
    if not stats.insights:
        return

    insight_lines = [line.strip() for line in stats.insights if line.strip()]
    if not insight_lines:
        return

    from app.services.wiki.vault_service import get_wiki_archiver

    archiver = get_wiki_archiver(llm, agent_id=agent_id)
    structure = archiver._structure

    date = datetime.now(UTC).strftime("%Y-%m-%d")
    safe_agent = "".join(c if c.isalnum() or c in "-_" else "_" for c in (agent_id or "default"))
    digest_source = "\n".join(insight_lines)
    digest_hash = hashlib.sha256(digest_source.encode()).hexdigest()[:8]
    relative_path = f"memory/consolidation_{safe_agent}_{date}_{digest_hash}.md"

    body_lines = ["# Consolidation insights", "", f"Date: {date}", ""]
    for index, insight in enumerate(insight_lines, start=1):
        body_lines.append(f"{index}. {insight}")
    content = "\n".join(body_lines) + "\n"

    frontmatter = (
        f"---\n"
        f"source: consolidation\n"
        f"bridge_source: consolidation_digest\n"
        f"agent_id: \"{agent_id or ''}\"\n"
        f"date: \"{date}\"\n"
        f"---\n\n"
    )

    result = await publish_raw(
        structure,
        RawPublishRequest(
            relative_path=relative_path,
            content=frontmatter + content,
            conflict_policy=RawConflictPolicy.PUT_IF_ABSENT,
        ),
        caller="chat",
    )
    if result.security_blocked:
        logger.warning("Consolidation wiki bridge blocked: %s", relative_path)
        return
    if not result.written:
        return

    archiver._compiler.enqueue_file(result.absolute_path)
    logger.info("Consolidation insights archived to wiki: %s", relative_path)
