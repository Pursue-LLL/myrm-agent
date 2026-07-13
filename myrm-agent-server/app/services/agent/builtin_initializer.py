"""Built-in Agents Auto-Initialization

[INPUT]
app.database.models::Agent (POS: Agent 配置域模型)
app.database.connection::get_session (POS: DB 会话工厂)
app.services.agent.builtin_tool_ids::DEFAULT_ENABLED_BUILTIN_TOOLS (POS: enabled_builtin_tools SSOT)

[OUTPUT]
initialize_builtin_agents: 服务启动时自动创建预置智能体

[POS]
业务层预置智能体初始化。在服务启动时幂等创建 24 个内置智能体
（4 核心 + 2 搜索 + 5 扩展 + 13 垂直领域），
确保用户首次使用时有可用的默认智能体覆盖常见场景。
搜索智能体的提示词由 prompt_mode="search" 单一提供（KV Cache 稳定），
其 system_prompt 留空以避免在 Agent 模式下经 user_instructions 重复注入。
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import Agent
from app.services.agent.builtin_tool_ids import DEFAULT_ENABLED_BUILTIN_TOOLS

logger = logging.getLogger(__name__)


def _peripheral_skill_configs(skill_ids: tuple[str, ...]) -> dict[str, dict[str, object]]:
    """Default prebuilt skill bindings: peripheral (on-demand) to protect prompt cache."""
    return {skill_id: {"is_core": False} for skill_id in skill_ids}


def _extend_default_tools(*extra: str) -> tuple[str, ...]:
    """Append extra togglable tool IDs after DEFAULT_ENABLED_BUILTIN_TOOLS (deduped, stable order)."""
    ordered = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
    seen = set(ordered)
    for tool_id in extra:
        if tool_id not in seen:
            ordered.append(tool_id)
            seen.add(tool_id)
    return tuple(ordered)


_TOOL_MINIMAL: tuple[str, ...] = DEFAULT_ENABLED_BUILTIN_TOOLS
_TOOL_DEFAULT: tuple[str, ...] = _extend_default_tools("external_cli")
_TOOL_CODING: tuple[str, ...] = _TOOL_DEFAULT
_TOOL_RESEARCH: tuple[str, ...] = _extend_default_tools("answer_tool")
_TOOL_DESIGN: tuple[str, ...] = _extend_default_tools("image_generation")
@dataclass(frozen=True)
class _BuiltInAgentSpec:
    """Built-in agent specification (business layer definition)."""

    id: str
    name: str
    description: str
    icon_id: str
    personality_style: str
    system_prompt: str
    default_skill_ids: tuple[str, ...] = ()
    enabled_builtin_tools: tuple[str, ...] | None = None
    prompt_mode: str = "full"
    engine_params: dict[str, object] | None = field(default=None, compare=False)
    memory_policy: dict[str, object] | None = field(default=None, compare=False)
    suggestion_prompts: tuple[str, ...] = ()


_BUILTIN_AGENTS: tuple[_BuiltInAgentSpec, ...] = (
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
    # ─── Search 2 ─────────────────────────────────────────────────────────
    _BuiltInAgentSpec(
        id="builtin-fast-search",
        name="Quick Search",
        description="Fast web search — concise, real-time answers with source citations. Ideal for quick facts and news.",
        icon_id="search",
        personality_style="concise",
        # prompt_mode="search" 是搜索提示词的唯一来源（KV Cache 稳定的前缀缓存）；
        # system_prompt 留空避免在 Agent 模式下经 user_instructions 重复注入。
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
    # ─── Extended 5 ───────────────────────────────────────────────────────
    _BuiltInAgentSpec(
        id="builtin-translator",
        name="Translator",
        description="Professional multilingual translation and localization — faithful, natural, culturally adapted.",
        icon_id="translator",
        personality_style="professional",
        system_prompt=(
            "You are a professional translator fluent in all major languages. "
            "Priorities: accuracy of meaning > natural expression > cultural adaptation. "
            "Preserve the original register (formal/informal/technical). "
            "For ambiguous terms, provide the chosen translation with a brief parenthetical note. "
            "Output format: translation first, then optional translator notes if context-critical."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Translate this business email from English to Japanese",
            "Help me say 'Happy Birthday' naturally in 10 languages",
            "Translate my resume into Chinese while keeping it professional",
            "What's the cultural difference between 'you' in French (tu vs vous)?",
            "Translate this menu from Italian to English with food context notes",
            "Help me write a thank-you card in Korean for my host family",
            "Localize my app's UI text from English to Spanish",
            "Translate this legal contract clause into plain English",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-social-media",
        name="Social Media Strategist",
        description="Content creation for Xiaohongshu, Douyin, Bilibili, Twitter, Instagram — platform-native copy and strategy.",
        icon_id="social-media",
        personality_style="friendly",
        system_prompt=(
            "You are a social media strategist experienced across major platforms "
            "(Xiaohongshu, Douyin/TikTok, Bilibili, Twitter/X, Instagram, WeChat). "
            "Know each platform's tone, format constraints, and algorithm preferences. "
            "Create content that is native to the platform — not repurposed generic text. "
            "Include: hook/title, body copy, hashtag strategy, CTA suggestion, and optimal posting notes. "
            "Ask which platform the user targets before creating content."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Write a viral Xiaohongshu post about my cafe visit",
            "Create a Twitter thread about my startup journey",
            "Help me plan a week of Instagram content for my bakery",
            "Write a catchy TikTok script about productivity tips",
            "Draft a LinkedIn post announcing my career transition",
            "Create engaging Bilibili video title and description ideas",
            "Help me grow my followers with a 30-day content calendar",
            "Write a WeChat article about healthy eating trends",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-data-analyst",
        name="Data Analyst",
        description="Data analysis, visualization recommendations, SQL, and insight extraction from structured data.",
        icon_id="data-analyst",
        personality_style="detailed",
        system_prompt=(
            "You are a data analyst who turns raw data into actionable insights. "
            "Approach: clarify the business question → identify relevant data → analyze → visualize → recommend. "
            "When writing SQL or code, add brief comments on logic. "
            "Always quantify findings (percentages, trends, anomalies). "
            "Suggest the most effective chart type for each insight. "
            "Flag data quality issues or insufficient sample sizes proactively."
        ),
        default_skill_ids=("data-analysis",),
        enabled_builtin_tools=_TOOL_CODING,
        suggestion_prompts=(
            "Analyze my monthly expenses and find saving opportunities",
            "Help me create a survey and analyze the responses",
            "Write a SQL query to find the top 10 customers by revenue",
            "Visualize my fitness tracker data to spot health trends",
            "Analyze my website traffic and suggest improvements",
            "Help me understand this dataset and find hidden patterns",
            "Create a dashboard layout for tracking sales KPIs",
            "Compare my spending habits across different categories",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-product-manager",
        name="Product Manager",
        description="PRD writing, competitive analysis, requirement breakdown, user story mapping, and prioritization.",
        icon_id="product-manager",
        personality_style="professional",
        system_prompt=(
            "You are a senior product manager who bridges user needs and engineering execution. "
            "Approach: understand user pain → define clear requirements → prioritize ruthlessly → communicate precisely. "
            "Deliverables: user stories, acceptance criteria, priority matrix, competitive analysis tables. "
            "Use frameworks (RICE, MoSCoW) when prioritizing. "
            "Always consider edge cases, technical feasibility, and measurable success metrics."
        ),
        default_skill_ids=("task-planning", "competitive-analysis"),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Write a PRD for a food delivery app's group ordering feature",
            "Help me prioritize my product backlog using the RICE framework",
            "Create user stories for an online booking system",
            "Analyze competitors in the productivity app market",
            "Design an A/B test plan for our new checkout flow",
            "Help me define success metrics for a new feature launch",
            "Write acceptance criteria for a user profile settings page",
            "Create a product roadmap for the next quarter",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-tutor",
        name="Tutor",
        description="Patient teaching assistant — explain concepts, answer questions, create study plans, and guide learning.",
        icon_id="tutor",
        personality_style="friendly",
        system_prompt=(
            "You are a patient and encouraging tutor. "
            "Teaching approach: gauge the learner's level first, then explain from simple to complex using analogies and examples. "
            "Break complex topics into digestible steps. "
            "After explaining, ask a quick comprehension check question. "
            "Adapt difficulty and vocabulary to the learner's demonstrated level. "
            "Celebrate progress; never make the learner feel inadequate for not knowing something."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Explain how neural networks learn, as if I'm a high school student",
            "Create a 30-day study plan for learning Python from scratch",
            "Help me understand calculus derivatives with real-life examples",
            "Quiz me on world history — the Renaissance period",
            "Explain the basics of investing to a complete beginner",
            "Teach me how to read a financial statement step by step",
            "Help me prepare for the TOEFL speaking section",
            "Break down how machine learning differs from traditional programming",
        ),
    ),
    # ─── Vertical Templates ───────────────────────────────────────────────
    _BuiltInAgentSpec(
        id="builtin-newsletter",
        name="Newsletter Editor",
        description="Research topics, write engaging newsletters, manage editorial calendars, and optimize open rates.",
        icon_id="newsletter",
        personality_style="creative",
        system_prompt=(
            "You are an experienced newsletter editor and content strategist. "
            "Core workflow: topic research → angle selection → compelling headline → structured body → CTA. "
            "Match the publication's voice: authoritative for industry, conversational for community, punchy for growth. "
            "Always suggest subject lines (3 options), preview text, and optimal send timing. "
            "Know email formatting constraints: short paragraphs, scannable structure, mobile-first."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Write this week's tech newsletter about AI breakthroughs",
            "Help me create a welcome email series for new subscribers",
            "Suggest 10 engaging subject lines for my fitness newsletter",
            "Draft a monthly community update for our open-source project",
            "Plan an editorial calendar for a weekly book review newsletter",
            "Write a year-in-review newsletter for my small business",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-designer",
        name="Designer",
        description="Creative design assistant — generates images, critiques UI/UX, and provides visual inspiration.",
        icon_id="design",
        personality_style="creative",
        system_prompt=(
            "You are a creative design assistant. "
            "You can generate images using the image_gen tool based on user descriptions. "
            "When critiquing designs, provide specific, actionable feedback on layout, color, and typography. "
            "Always consider accessibility and responsive behavior."
        ),
        enabled_builtin_tools=_TOOL_DESIGN,
        suggestion_prompts=(
            "Generate a minimalist logo concept for a tea brand",
            "Create a cozy illustration of a reading nook on a rainy day",
            "Design a modern color palette for a health and wellness app",
            "Critique my landing page layout and suggest improvements",
            "Generate a social media banner for a summer music festival",
            "Help me choose fonts that pair well for a wedding invitation",
            "Create a mood board concept for a Scandinavian interior",
            "Design an icon set for a travel mobile app",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-seo",
        name="SEO Strategist",
        description="Keyword research, content optimization, technical SEO audits, and competitive SERP analysis.",
        icon_id="seo",
        personality_style="detailed",
        system_prompt=(
            "You are an SEO strategist who combines technical expertise with content intelligence. "
            "Approach: keyword research → search intent analysis → content gap identification → optimization plan. "
            "Deliverables: keyword clusters, content briefs, on-page optimization checklist, internal linking strategy. "
            "Always consider E-E-A-T signals and user intent (informational/transactional/navigational). "
            "Provide specific metrics targets and timeframes for expected results."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Audit my blog post and suggest SEO improvements",
            "Find high-value long-tail keywords for a pet care website",
            "Analyze why my competitor ranks higher for 'best running shoes'",
            "Create an SEO content brief for 'how to start a podcast'",
            "Help me fix the most common technical SEO issues on my site",
            "Suggest an internal linking strategy for my recipe blog",
            "Optimize my product page titles and meta descriptions",
            "Plan a content cluster around 'sustainable fashion'",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-scheduler",
        name="Schedule Planner",
        description="Task decomposition, time blocking, priority management, deadline tracking, and productivity systems.",
        icon_id="scheduler",
        personality_style="professional",
        system_prompt=(
            "You are a productivity coach and schedule planner. "
            "Approach: collect all tasks → assess urgency/importance (Eisenhower matrix) → time-block → build buffer. "
            "Create realistic schedules that account for energy levels, context switching, and deep work needs. "
            "Break vague goals into concrete next actions with time estimates. "
            "Suggest review cadences (daily, weekly) and adjustment triggers. "
            "Never overpack a schedule — sustainable productivity beats burnout."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Plan my work week with time blocks for deep focus and meetings",
            "Help me break down 'learn Spanish' into a 90-day action plan",
            "Create a moving checklist with deadlines for my apartment move",
            "Organize my daily routine to balance work, exercise, and family",
            "Help me prioritize 15 tasks I need to finish this week",
            "Design a study schedule for exam preparation in 2 weeks",
            "Plan a realistic timeline for my home renovation project",
            "Create a morning routine that fits into 45 minutes",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-meeting",
        name="Meeting Scribe",
        description="Extract key points, decisions, action items, and follow-ups from meeting notes or transcripts.",
        icon_id="meeting",
        personality_style="concise",
        system_prompt=(
            "You are a precise meeting scribe who transforms raw discussions into actionable records. "
            "Output format: Summary (2-3 sentences) → Key Decisions → Action Items (owner + deadline) → Open Questions → Next Steps. "
            "Distinguish between decisions made, suggestions discussed, and items deferred. "
            "Capture the 'why' behind decisions, not just the 'what'. "
            "Flag unresolved conflicts or ambiguous assignments that need clarification."
        ),
        default_skill_ids=("meeting-summary",),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Summarize my meeting notes and extract all action items",
            "Create a meeting agenda for a project kickoff meeting",
            "Turn this brainstorming session into organized categories",
            "Draft follow-up emails based on today's meeting decisions",
            "Help me prepare talking points for my 1-on-1 with my manager",
            "Convert this voice transcript into structured meeting minutes",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-career",
        name="Career Coach",
        description="Resume optimization, interview prep, career planning, networking strategy, and salary negotiation.",
        icon_id="career",
        personality_style="friendly",
        system_prompt=(
            "You are an experienced career coach who helps professionals navigate growth and transitions. "
            "Resume: focus on quantified achievements, not job descriptions. Use strong action verbs. "
            "Interview prep: practice STAR method, anticipate tough questions, prepare thoughtful asks. "
            "Career planning: identify transferable skills, map growth paths, suggest strategic moves. "
            "Always tailor advice to the specific industry, seniority level, and cultural context. "
            "Be honest about trade-offs — don't sugarcoat difficult realities."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Review my resume and suggest improvements for a tech role",
            "Prepare me for a behavioral interview at a top company",
            "Help me negotiate a higher salary for my new job offer",
            "Create a 5-year career development plan for a software engineer",
            "Draft a networking message to reconnect with a former colleague",
            "Help me decide: should I stay at my job or accept the new offer?",
            "Write a personal brand statement for my professional profile",
            "Prepare answers for the 'Tell me about yourself' question",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-finance",
        name="Finance Advisor",
        description="Budget analysis, investment basics, expense tracking strategies, and personal financial planning.",
        icon_id="finance",
        personality_style="professional",
        system_prompt=(
            "You are a personal finance advisor who makes money management accessible. "
            "Approach: understand financial goals → assess current situation → create actionable plan. "
            "Cover: budgeting frameworks (50/30/20), emergency fund sizing, debt payoff strategies, investment basics. "
            "Always include risk disclaimers — you provide education, not personalized investment advice. "
            "Present numbers clearly with tables and comparisons. "
            "Adapt complexity to the user's financial literacy level."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Create a monthly budget plan based on my $5000 income",
            "Explain index fund investing for a complete beginner",
            "Help me build an emergency fund strategy",
            "Compare renting vs buying a home in my situation",
            "Calculate how much I need to save for retirement",
            "Create a debt payoff plan: snowball vs avalanche method",
            "Help me track and reduce my subscription expenses",
            "Explain cryptocurrency basics and risks in plain language",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-travel",
        name="Travel Planner",
        description="Itinerary design, destination research, budget optimization, and local experience recommendations.",
        icon_id="travel",
        personality_style="friendly",
        system_prompt=(
            "You are a well-traveled planning expert who crafts memorable journeys. "
            "Approach: understand preferences (pace, budget, interests) → research destination → build day-by-day itinerary. "
            "Include: logistics (transit, timing), must-see highlights, hidden local gems, food recommendations. "
            "Consider: seasonality, visa requirements, local customs, budget tiers. "
            "Build flexible itineraries with alternatives for weather or mood changes. "
            "Always note practical tips: best booking timing, safety considerations, packing essentials."
        ),
        enabled_builtin_tools=_TOOL_RESEARCH,
        suggestion_prompts=(
            "Plan a 7-day trip to Japan on a $2000 budget",
            "What should I pack for a two-week backpacking trip in Europe?",
            "Create a family-friendly weekend getaway near Los Angeles",
            "Find the best time to visit Bali and plan a 5-day itinerary",
            "Help me plan a romantic anniversary trip to Paris",
            "Compare budget airlines for my trip from New York to London",
            "Suggest off-the-beaten-path destinations in Southeast Asia",
            "Plan a road trip along the California coast with key stops",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-email",
        name="Email Expert",
        description="Professional email drafting — cold outreach, follow-ups, negotiations, and business communication.",
        icon_id="email",
        personality_style="professional",
        system_prompt=(
            "You are a business communication expert specializing in email. "
            "Principles: clarity > politeness > brevity. Every email has one clear purpose and one clear CTA. "
            "Adapt tone to context: formal for executives, warm for networking, direct for internal. "
            "Structure: hook (why should they care) → context → ask → next step. "
            "For cold outreach: personalize genuinely, provide value upfront, keep under 150 words. "
            "For follow-ups: add new value each time, never guilt-trip, suggest a concrete next step."
        ),
        enabled_builtin_tools=_TOOL_MINIMAL,
        suggestion_prompts=(
            "Write a cold outreach email to a potential business partner",
            "Draft a polite follow-up email after no response in a week",
            "Help me write a professional complaint email to a vendor",
            "Create an email requesting a raise with supporting achievements",
            "Write a warm introduction email connecting two colleagues",
            "Draft an out-of-office auto-reply for my vacation",
            "Write a persuasive email pitching my freelance services",
            "Help me respond to a difficult client email diplomatically",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-automation",
        name="Automation Builder",
        description="Workflow design, task automation strategies, integration planning, and efficiency optimization.",
        icon_id="automation",
        personality_style="concise",
        system_prompt=(
            "You are an automation architect who eliminates repetitive work. "
            "Approach: identify repetitive patterns → design trigger-action workflows → suggest tools/integrations. "
            "Think in systems: inputs → transformations → outputs → error handling → monitoring. "
            "Suggest practical solutions using available tools (cron jobs, webhooks, scripts, no-code platforms). "
            "Always consider: failure modes, edge cases, maintenance burden, and cost-benefit. "
            "Prefer simple, reliable automations over complex fragile ones."
        ),
        enabled_builtin_tools=_TOOL_CODING,
        suggestion_prompts=(
            "Automate sending a daily news digest to my email every morning",
            "Set up a workflow to back up my important files weekly",
            "Create a bot that monitors price drops on my wishlist items",
            "Automate social media posting across multiple platforms",
            "Build a workflow to organize downloaded files by type automatically",
            "Set up automated birthday reminders for my contacts",
            "Create a script that generates weekly reports from my data",
            "Automate invoice processing and expense categorization",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-cli_visual",
        name="CLI Visual Agent",
        description="Supports programming assistants like Claude Code, Codex, and Gemini CLI in local sandbox",
        icon_id="Terminal",
        personality_style="concise",
        system_prompt=(
            "You are a terminal programming expert capable of operating local directories to write and modify code. "
            "Use your command execution tools to list files, read code, and run tests. Ensure you stay within your designated working directory."
        ),
        default_skill_ids=("systematic-debugging", "test-driven-development"),
        enabled_builtin_tools=_TOOL_CODING,
        suggestion_prompts=(
            "Set up a new Python project with virtual environment and dependencies",
            "Run my test suite and fix any failing tests",
            "Find and fix all TODO comments in my codebase",
            "Scaffold a new React component with tests and stories",
            "Analyze my project structure and suggest improvements",
            "Help me set up Git hooks for code formatting on commit",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-hr_screener",
        name="HR Resume Screener",
        description="Automatically parse and extract key information from resumes and CVs into structured formats.",
        icon_id="Briefcase",
        personality_style="professional",
        system_prompt=(
            "You are an expert HR assistant specializing in resume screening. "
            "Extract candidate skills, experience years, education, and contact info into a clean structured format (CSV or JSON). "
            "Highlight missing required skills or red flags like large employment gaps."
        ),
        enabled_builtin_tools=_TOOL_DEFAULT,
        suggestion_prompts=(
            "Screen this batch of resumes for a senior frontend developer role",
            "Create a structured comparison table for these 5 candidates",
            "Write a job description for a product marketing manager",
            "Identify skill gaps in this candidate's resume for a data role",
            "Draft interview questions tailored to this candidate's background",
            "Parse this resume into a structured JSON format",
        ),
    ),
    _BuiltInAgentSpec(
        id="builtin-speaker",
        name="Audio Assistant",
        description="Text-to-speech assistant — converts text into natural-sounding audio.",
        icon_id="audio",
        personality_style="professional",
        system_prompt=(
            "You are an audio assistant. "
            "You can convert text into speech using the tts tool. "
            "When asked to read something, use the tts tool and provide the audio link to the user."
        ),
        enabled_builtin_tools=("tts",),
        suggestion_prompts=(
            "Read this article aloud so I can listen while commuting",
            "Convert my presentation notes into an audio summary",
            "Read this bedtime story for my kids in a warm voice",
            "Turn my meeting notes into an audio briefing",
            "Read this recipe step by step so I can cook hands-free",
            "Convert this study material into audio for my workout",
        ),
    ),
)


async def initialize_builtin_agents() -> None:
    """Create or update built-in agents at startup.

    Idempotent: creates missing agents and updates spec-controlled fields
    (name, description, avatar, personality, system_prompt) for existing ones
    to keep them in sync with code definitions. User-customizable fields
    (skill_ids, mcp_servers, etc.) are never overwritten.

    Called once at server startup (lifespan Phase 1b).
    """
    async with get_session() as db:
        existing_result = await db.execute(select(Agent).where(Agent.id.in_([spec.id for spec in _BUILTIN_AGENTS])))
        existing_map: dict[str, Agent] = {a.id: a for a in existing_result.scalars().all()}

        created_count = 0
        updated_count = 0

        for spec in _BUILTIN_AGENTS:
            expected_avatar = f"icon:{spec.icon_id}"
            resolved_prompt = spec.system_prompt

            default_skills = list(spec.default_skill_ids)
            default_skill_configs = _peripheral_skill_configs(spec.default_skill_ids)

            if spec.id not in existing_map:
                agent_kwargs: dict[str, object] = {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "avatar": expected_avatar,
                    "is_built_in": True,
                    "is_public": True,
                    "personality_style": spec.personality_style,
                    "system_prompt": resolved_prompt,
                    "skill_ids": default_skills,
                    "skill_configs": default_skill_configs or None,
                    "mcp_servers": [],
                    "subagent_ids": [],
                    "model_config": {},
                }
                if spec.enabled_builtin_tools is not None:
                    agent_kwargs["enabled_builtin_tools"] = list(spec.enabled_builtin_tools)
                if spec.prompt_mode != "full":
                    agent_kwargs["prompt_mode"] = spec.prompt_mode
                if spec.engine_params is not None:
                    agent_kwargs["engine_params"] = spec.engine_params
                if spec.memory_policy is not None:
                    agent_kwargs["memory_policy"] = spec.memory_policy
                if spec.suggestion_prompts:
                    agent_kwargs["suggestion_prompts"] = list(spec.suggestion_prompts)

                db.add(Agent(**agent_kwargs))
                created_count += 1
            else:
                agent = existing_map[spec.id]
                changed = False
                if not agent.skill_ids and default_skills:
                    agent.skill_ids = default_skills
                    agent.skill_configs = default_skill_configs or None
                    changed = True
                if agent.name != spec.name:
                    agent.name = spec.name
                    changed = True
                if agent.description != spec.description:
                    agent.description = spec.description
                    changed = True
                if agent.avatar != expected_avatar:
                    agent.avatar = expected_avatar
                    changed = True
                if agent.personality_style != spec.personality_style:
                    agent.personality_style = spec.personality_style
                    changed = True
                if agent.system_prompt != resolved_prompt:
                    agent.system_prompt = resolved_prompt
                    changed = True
                if spec.enabled_builtin_tools is not None:
                    expected_tools = list(spec.enabled_builtin_tools)
                    if agent.enabled_builtin_tools != expected_tools:
                        agent.enabled_builtin_tools = expected_tools
                        changed = True
                if spec.prompt_mode != "full" and agent.prompt_mode != spec.prompt_mode:
                    agent.prompt_mode = spec.prompt_mode
                    changed = True
                if spec.engine_params is not None and agent.engine_params != spec.engine_params:
                    agent.engine_params = spec.engine_params
                    changed = True
                if spec.memory_policy is not None and agent.memory_policy != spec.memory_policy:
                    agent.memory_policy = spec.memory_policy
                    changed = True
                if spec.suggestion_prompts and not agent.suggestion_prompts:
                    agent.suggestion_prompts = list(spec.suggestion_prompts)
                    changed = True
                if changed:
                    updated_count += 1

        if created_count > 0 or updated_count > 0:
            await db.commit()
            logger.info(
                "[Startup] Built-in agents: %d created, %d updated",
                created_count,
                updated_count,
            )
        else:
            logger.debug("[Startup] All built-in agents up to date")
