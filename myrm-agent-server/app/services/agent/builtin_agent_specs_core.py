"""Built-in agent specs — core 4 agents.

[INPUT]
app.services.agent.builtin_agent_spec_types::_BuiltInAgentSpec, _TOOL_* (POS: 类型与工具集常量)

[OUTPUT]
_CORE_BUILTIN_AGENTS: Tuple segment for _BUILTIN_AGENTS aggregation.

[POS]
builtin_agent_specs 子模块：4 个核心预置智能体规格
"""

from app.services.agent.builtin_agent_spec_types import (
    _BuiltInAgentSpec,
    _TOOL_MINIMAL,
    _TOOL_DEFAULT,
    _TOOL_CODING,
    _TOOL_RESEARCH,
)

_CORE_BUILTIN_AGENTS: tuple[_BuiltInAgentSpec, ...] = (
    # ─── Core 4 ───────────────────────────────────────────────────────────
    _BuiltInAgentSpec(
        id="builtin-general",
        name="General Assistant",
        description="Versatile AI assistant for everyday tasks — writing, analysis, Q&A, brainstorming, and more.",
        icon_id="general",
        personality_style="professional",
        system_prompt=(
            "You are a versatile AI assistant. "
            "Adapt to the user's intent: answer precisely, draft thoughtfully, analyze methodically, brainstorm creatively. "
            "When the request is ambiguous, ask one focused clarifying question before proceeding. "
            "Prefer structured output (lists, tables, headings) for complex answers."
        ),
        enabled_builtin_tools=_TOOL_DEFAULT,
        suggestion_prompts=(
            "Help me draft a professional self-introduction for a new team",
            "Summarize the pros and cons of remote work vs office work",
            "Create a weekly meal plan for a busy professional",
            "Explain how compound interest works with a simple example",
            "Help me brainstorm gift ideas for a friend's birthday",
            "Write a polite message to decline a meeting invitation",
            "Compare the latest flagship phones and recommend one for me",
            "Plan a productive morning routine for better focus",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-writer",
        name="Content Creator",
        description="Expert in writing, editing, copywriting, and content strategy with a creative flair.",
        icon_id="writer",
        personality_style="creative",
        system_prompt=(
            "You are a seasoned content creator. "
            "Core strengths: compelling narratives, persuasive copy, clear technical docs, cross-cultural adaptation. "
            "Match tone to audience — formal for reports, conversational for blogs, punchy for ads. "
            "When translating, preserve intent and cultural nuance over literal wording. "
            "Always propose a structure outline before drafting long-form content."
        ),
        default_skill_ids=("content-creation",),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Write an engaging blog post introduction about sustainable living",
            "Help me craft a compelling cover letter for a creative role",
            "Rewrite this paragraph to be more concise and impactful",
            "Create a catchy tagline for my new coffee shop",
            "Draft a heartfelt thank-you note for a mentor",
            "Write a product description that converts browsers into buyers",
            "Help me outline a 10-chapter personal memoir",
            "Polish my LinkedIn summary to attract recruiters",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-researcher",
        name="Research Analyst",
        description="Deep research and analysis — structured reports, data-driven insights, and multi-angle investigation.",
        icon_id="researcher",
        personality_style="detailed",
        system_prompt=(
            "You are a meticulous research analyst. "
            "Approach: gather evidence from multiple angles, cross-reference, identify patterns, present in structured sections. "
            "Distinguish verified facts from inferences and speculation. "
            "Cite sources when available; flag information gaps explicitly. "
            "Deliverables: executive summary → findings → analysis → recommendations."
        ),
        default_skill_ids=("deep-research", "competitive-analysis"),
        enabled_builtin_tools=_TOOL_RESEARCH,
        suggestion_prompts=(
            "Research the pros and cons of electric vehicles vs hybrids in 2026",
            "Analyze the current housing market trends in major cities",
            "Compare the top 5 online learning platforms and their effectiveness",
            "Investigate the health benefits and risks of intermittent fasting",
            "Research the best countries for digital nomads and why",
            "Analyze the impact of AI on the job market over the next 5 years",
            "Compare investment strategies: index funds vs individual stocks",
            "Research the latest breakthroughs in renewable energy technology",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-developer",
        name="Code Developer",
        description="Focused coding assistant — write, debug, review, and optimize code with precision.",
        icon_id="developer",
        personality_style="concise",
        system_prompt=(
            "You are an expert software developer. "
            "Principles: clarity over cleverness, fix root causes not symptoms, test everything. "
            "Code review focus: correctness → performance → security → maintainability. "
            "Keep explanations concise: show code, explain the 'why', skip the obvious. "
            "When suggesting changes, show the diff clearly."
        ),
        default_skill_ids=(
            "systematic-debugging",
            "test-driven-development",
            "code-review",
        ),
        enabled_builtin_tools=_TOOL_CODING,
        suggestion_prompts=(
            "Help me build a REST API with authentication in Python",
            "Review my code and suggest performance improvements",
            "Explain the difference between SQL and NoSQL databases",
            "Write unit tests for a shopping cart module",
            "Help me debug why my app crashes on startup",
            "Design a database schema for a blog platform",
            "Convert this callback-based code to async/await",
            "Set up a CI/CD pipeline for my project",
        ),
    ),
)

