"""Per-turn knowledge pack retrieval for General Agent streams.

[INPUT]
- app.ai_agents.agents::GeneralAgentParams (POS: General Agent 单轮执行参数)
- app.services.wiki.knowledge_pack::resolve_proactive_snippets_from_vaults (POS: 按问题从已挂载知识库检索并预算片段)
- app.services.wiki.vault::resolve_shared_wiki_vault_labels, resolve_shared_wiki_vault_paths (POS: 共享 Wiki Vault 路径与标签解析)

[OUTPUT]
- resolve_turn_knowledge_pack(): 当前问题的已挂载知识库片段 payload（None 表示本轮没有可注入片段）

[POS]
每轮知识包检索器。按本轮用户问题实时检索，结果经 run context 交给 harness 的 Human 尾部注入；不进入按会话缓存的 Memory Brief，因为知识包随问题变化。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai_agents.agents import GeneralAgentParams

logger = logging.getLogger(__name__)

_RETRIEVAL_TIMEOUT_SECONDS = 0.150


def _query_text(params: GeneralAgentParams) -> str:
    if isinstance(params.query, str):
        return params.query
    if isinstance(params.query, list):
        return " ".join(
            str(item.get("text", "")) for item in params.query if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


async def resolve_turn_knowledge_pack(params: GeneralAgentParams) -> dict[str, object] | None:
    """Retrieve snippets of the mounted knowledge bases for this turn's question.

    Follows the memory switches: nothing is retrieved when memory is off or the chat is incognito.
    Retrieval is bounded by ``_RETRIEVAL_TIMEOUT_SECONDS``; failures degrade to no pack.
    """
    if not params.enable_memory or params.incognito_mode or not params.memory_shared_context_ids:
        return None
    query = _query_text(params)
    if not query.strip():
        return None

    try:
        from app.services.wiki.knowledge_pack import resolve_proactive_snippets_from_vaults
        from app.services.wiki.vault import (
            resolve_shared_wiki_vault_labels,
            resolve_shared_wiki_vault_paths,
        )

        vault_paths = resolve_shared_wiki_vault_paths(params.memory_shared_context_ids, must_exist=True)
        if not vault_paths:
            return None

        result = await resolve_proactive_snippets_from_vaults(
            query=query,
            vault_paths=vault_paths,
            vault_labels=resolve_shared_wiki_vault_labels(
                params.memory_shared_context_ids,
                context_name_map=params.memory_shared_context_names,
            ),
            timeout_seconds=_RETRIEVAL_TIMEOUT_SECONDS,
        )
        if result.snippets:
            return result.to_dict()
    except Exception as exc:
        logger.warning("Knowledge pack retrieval failed; the turn continues without it: %s", exc)
    return None
