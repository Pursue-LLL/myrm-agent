"""Built-in agent specs — search 2 agents.

[INPUT]
app.services.agent.builtin_agent_spec_types::_BuiltInAgentSpec, _TOOL_* (POS: 类型与工具集常量)

[OUTPUT]
_SEARCH_BUILTIN_AGENTS: Tuple segment for _BUILTIN_AGENTS aggregation.

[POS]
builtin_agent_specs 子模块：2 个搜索预置智能体规格
"""

from app.services.agent.builtin_agent_spec_types import (
    _BuiltInAgentSpec,

)

_SEARCH_BUILTIN_AGENTS: tuple[_BuiltInAgentSpec, ...] = (
    # ─── Search 2 ─────────────────────────────────────────────────────────
    _BuiltInAgentSpec(
        id="builtin-fast-search",
        name="Quick Search",
        description="Fast web search — concise, real-time answers with source citations. Ideal for quick facts and news.",
        icon_id="search",
        personality_style="concise",
        system_prompt="",
        enabled_builtin_tools=("web_search",),
        prompt_mode="search",
        engine_params={"max_tool_calls": 8, "recursion_limit": 30},
        memory_policy={"write_policy": "conversation"},
        suggestion_prompts=(
            "What happened in the world today?",
            "What's the current weather in Tokyo?",
            "Find the latest reviews for the new iPhone",
            "What are today's top trending topics on social media?",
            "Look up the exchange rate between USD and EUR",
            "What are the showtimes for movies near me this weekend?",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-deep-search",
        name="Deep Search",
        description="Thorough multi-source research — reads full pages, cross-references, and self-validates answers.",
        icon_id="search-deep",
        personality_style="detailed",
        system_prompt="",
        enabled_builtin_tools=("web_search", "answer_tool"),
        prompt_mode="search",
        engine_params={"max_tool_calls": 20, "recursion_limit": 50},
        memory_policy={"write_policy": "conversation"},
        suggestion_prompts=(
            "Deep dive into the current state of quantum computing research",
            "Find and compare all major AI coding assistants available in 2026",
            "Research the complete history and future outlook of space tourism",
            "Investigate the global supply chain challenges and emerging solutions",
            "Comprehensive analysis of the best cities to start a tech startup",
            "Research all sides of the debate on universal basic income",
        ),
    ),
)

