"""Agent core rules — the behavior rules every agent's system prompt carries.

One rule block serves every model: the behavior rules never vary with the model's name, so swapping the model leaves
them untouched and the KV-Cache prefix stable. Model quirks such as a tool call written as plain text are handled in
code (tool-call parsers, stream recovery), not by per-vendor prompt text.

Architecture:
    AGENT_CORE_RULES — anti-narration + tool honesty + anti-negative-claim
        + proactive grounding search + XML tool-call defense
        + context-first check + proactive capability discovery (all models)
    resolve_escalation_contract() — conditional model self-upgrade contract
        Only injected when escalation_target_llm differs from current model.
        Guides the model to emit <<<NEEDS_PRO>>> when tasks exceed its tier.

All output is fixed text (determined at init time), fully KV-Cache-safe.

See: agent/context_management/PROMPT_CACHE_PRACTICE.md §2.2

[INPUT]
- langchain_core.language_models::BaseChatModel (POS: LangChain chat model base class)

[OUTPUT]
- AGENT_CORE_RULES: behavior rules constant (anti-narration + tool honesty + anti-negative-claim + proactive grounding search + XML defense + context-first + proactive capability discovery)
- resolve_escalation_contract(): conditional escalation contract resolver

[POS]
Agent core rules and escalation contract: the one rule block every agent gets, plus a conditional self-upgrade
contract when an escalation target model is configured.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

# ============================================================================
# Core Agent Rules (all models, always injected)
# ============================================================================

AGENT_CORE_RULES = (
    "\n<agent_behavior_rules>"
    "NEVER narrate or announce tool usage in text. "
    'Do NOT say "让我查一下…", "I will use…", "搜索中…", or similar. '
    "Tool calls are infrastructure, not conversation — give the FINAL ANSWER directly."
    " NEVER fabricate or guess tool results. "
    'Empty results → say "No results found." '
    "Failures → report the error, never make up data."
    " Before asserting absence — Negative claims ('X is missing', 'there is no Z') — "
    "use a verification tool to confirm. "
    "If the tool returns nothing, state the absence WITH the tool name and "
    "query as evidence (e.g. \"No callers of foo() found (grep 'foo')\"). "
    "If no verification tool is available, qualify: "
    '"I have not verified this — it may be inaccurate."'
    " When a search tool is available, ALWAYS search before asserting facts about: (1) entities released or updated "
    "after your knowledge cutoff, (2) unfamiliar proper nouns or product names, "
    "(3) current prices, versions, or live events, (4) any claim you cannot verify "
    "from memory with certainty. Prefer one fast search over a confident but wrong answer."
    " Use ONLY the native Function Calling API. "
    "NEVER output <tool_call> or similar XML tags in response text."
    " Before calling any tool, check if the answer is already in the "
    "conversation context. Avoid redundant tool calls for information already present."
    " Before declining a user request due to missing capability, check if any "
    "discovery or search tool is available to find matching skills or tools."
    "</agent_behavior_rules>"
)


def _extract_model_name(llm: BaseChatModel) -> str:
    """Lowercase model name of a LangChain LLM instance ("" when it exposes no string name)."""
    for attr in ("model_name", "model"):
        name = getattr(llm, attr, "")
        if isinstance(name, str) and name:
            return name.lower()
    return ""


_ESCALATION_CONTRACT_TEMPLATE = (
    "\n<escalation_contract>"
    "You are running on `{current_model}`. A stronger model (`{target_model}`) is "
    "available for automatic escalation.\n"
    "If a task CLEARLY exceeds what you can do well — complex multi-domain reasoning, "
    "subtle correctness/safety/concurrency invariants you cannot resolve with confidence, "
    "or a design trade-off you would be guessing at — output this marker as the VERY "
    "FIRST line of your response (nothing before it):\n"
    "- `<<<NEEDS_PRO>>>` — bare marker\n"
    "- `<<<NEEDS_PRO: <one-sentence reason>>>` — preferred; the reason is shown to the user\n\n"
    "Do NOT emit any other content when you request escalation. "
    "Use this sparingly: normal tasks — answering questions, small operations, "
    "clear instructions, straightforward tool usage — stay on this tier. "
    "Request escalation ONLY when you would otherwise produce a guess or a "
    "visibly-mediocre answer."
    "</escalation_contract>"
)


def resolve_escalation_contract(llm: BaseChatModel, target_llm: BaseChatModel | None) -> str:
    """Resolve the escalation contract prompt for the given LLM pair.

    Returns a fixed string to append to the system prompt when the current
    model differs from the escalation target. Returns empty string when
    no escalation is configured or current == target (zero overhead).

    KV-Cache safe: output is determined at init time and never changes.
    """
    if target_llm is None:
        return ""

    current = _extract_model_name(llm)
    target = _extract_model_name(target_llm)

    if not current or not target or current == target:
        return ""

    return _ESCALATION_CONTRACT_TEMPLATE.format(current_model=current, target_model=target)
