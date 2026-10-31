"""Per-turn knowledge pack: snippets of the mounted knowledge bases for the current question.

The server retrieves the snippets for each turn's question and hands them over through the run
context. This middleware appends them, wrapped as untrusted data, to the tail of the final
HumanMessage. The SystemMessage and the history before that message are never touched. The block is
not persisted, so the next turn recomputes the previous turn's reply and tool results, like the other
Human-tail blocks (session deltas, base context).

[INPUT]
- toolkits.memory.config::RecallMode (POS: Memory configuration — functional switches and retrieval params only.)
- toolkits.memory.ephemeral_delta.tail_injector::append_block_to_last_human (POS: Tail-of-turn injection primitive.)
- agent.security.detection.content_boundary::sanitize, wrap_untrusted (POS: Untrusted content folding, marker neutralization, randomized UNTRUSTED_DATA envelopes.)

[OUTPUT]
- PROACTIVE_PACK_CONTEXT_KEY: run-context key under which the server passes the pack payload.
- format_proactive_pack: renders a pack payload into one untrusted-data block.
- proactive_pack_middleware: AgentMiddleware appending the pack block to the Human tail before each model call.

[POS]
Human-tail injection of the turn's knowledge-base snippets; follows the memory-recall switches (no manager or RecallMode.TOOLS means no injection).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from myrm_agent_harness.agent.security.detection.content_boundary import sanitize, wrap_untrusted
from myrm_agent_harness.toolkits.memory.config import RecallMode
from myrm_agent_harness.toolkits.memory.ephemeral_delta.tail_injector import append_block_to_last_human

from .memory_context_budget import escape_xml_item

PROACTIVE_PACK_CONTEXT_KEY = "proactive_knowledge_pack"

# The block is rendered once per turn and kept in the run context: ``wrap_untrusted`` draws a random
# boundary id per call, while every model call of the tool loop must send byte-identical tail text.
_RENDERED_BLOCK_KEY = "proactive_knowledge_pack_block"
_PACK_SECTION_TITLE = "Active Knowledge Pack Snippets (authoritative context)"


def format_proactive_pack(pack: Mapping[str, object]) -> str | None:
    """Render the pack snippets as one untrusted-data block; ``None`` when no snippet carries text."""
    snippets = pack.get("snippets")
    if not isinstance(snippets, list):
        return None

    items: list[str] = []
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        kb_name = sanitize(str(snippet.get("kb_name", "Knowledge Base")))
        title = sanitize(str(snippet.get("article_title", "General")))
        snippet_text = sanitize(str(snippet.get("snippet", "")))
        claim_text = sanitize(str(snippet.get("claim_text", "")).strip())
        claim_status = str(snippet.get("claim_status", "")).strip().lower()

        # Verified claims lead with a "Verified" label so the model weighs them above plain excerpts.
        if claim_text and claim_status in ("verified", "supported"):
            prefix = f"[{kb_name} | {title} | Verified: {claim_text}]"
        elif claim_text:
            prefix = f"[{kb_name} | {title} | Claim: {claim_text}]"
        else:
            prefix = f"[{kb_name} | {title}]"

        if snippet_text:
            items.append(f"{prefix} {snippet_text}")
        elif claim_text:
            items.append(prefix)

    if not items:
        return None
    body = "\n".join(f"- {escape_xml_item(item)}" for item in items)
    return wrap_untrusted(f"## {_PACK_SECTION_TITLE}\n{body}", source="knowledge_pack")


class ProactivePackMiddleware(AgentMiddleware):
    """Append the turn's knowledge pack to the final HumanMessage; nothing is persisted to the thread."""

    name = "proactive_pack_middleware"

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        context = getattr(request.runtime, "context", None) if request.runtime else None
        if not isinstance(context, dict):
            return await handler(request)
        pack = context.get(PROACTIVE_PACK_CONTEXT_KEY)
        if not isinstance(pack, Mapping):
            return await handler(request)

        from myrm_agent_harness.agent.skill_agent.context import get_memory_manager

        manager = get_memory_manager()
        if manager is None or manager.recall_mode == RecallMode.TOOLS:
            return await handler(request)

        block = context.get(_RENDERED_BLOCK_KEY)
        if not isinstance(block, str):
            block = format_proactive_pack(pack) or ""
            context[_RENDERED_BLOCK_KEY] = block
        if block:
            request = request.override(messages=append_block_to_last_human(request.messages, block))
        return await handler(request)


proactive_pack_middleware = ProactivePackMiddleware()
