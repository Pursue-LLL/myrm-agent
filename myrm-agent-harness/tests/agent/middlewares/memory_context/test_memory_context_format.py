"""What the memory block says: its sections, their fixed order, the veto lines, the scope boundary and the budget cut.

[INPUT]
- agent.middlewares.memory_context.memory_context_format::_format_memory_context (POS: renders the context the store handed out into the block's text)
- agent.middlewares.memory_context.memory_context_format::_has_memory_context (POS: tells the block the middleware built from any other message)

[POS]
Formatter guard for the memory block: cold start, profile, instructions, rules, vetoes, tool guidance and the budget cut.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import (
    _COLD_START_CONTEXT,
    MEMORY_CONTEXT_MARKER,
    _format_memory_context,
    _has_memory_context,
    _memory_context_message,
)

# ---------------------------------------------------------------------------
# _has_memory_context
# ---------------------------------------------------------------------------


def test_has_memory_context_recognises_only_the_block_the_middleware_built():
    text = "<user_memory_context>\nUser info\n</user_memory_context>"

    assert _has_memory_context([SystemMessage(content="System prompt"), _memory_context_message(text)]) is True
    # Same text without the flag is somebody else's message, not the block.
    assert _has_memory_context([SystemMessage(content="System prompt"), SystemMessage(content=text)]) is False
    assert _has_memory_context([SystemMessage(content="System prompt"), HumanMessage(content="Hello")]) is False


def test_has_memory_context_skips_non_string_parts():
    """Multimodal / structured content must not crash idempotency scan."""
    block = [{"type": "text", "text": "hello"}]
    msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content=block),
    ]
    assert _has_memory_context(msgs) is False


def test_format_memory_context_budget_truncates_oversized_memory():
    """A profile far larger than the budget is cut, and the block says so."""
    wall = "w" * 1200
    ctx = {"global_profile": {f"k{i}": wall for i in range(60)}}
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert "... (Some lower-priority memory items were truncated" in stable


def test_format_truncation_notice_omits_tool_guidance_when_not_bound():
    """CONTEXT mode truncation notice must not reference the unbound memory_search_tool."""
    wall = "w" * 1200
    ctx = {"global_profile": {f"k{i}": wall for i in range(60)}}
    stable = _format_memory_context(ctx, memory_search_enabled=False).text
    assert stable is not None
    assert "... (Some lower-priority memory items were truncated" in stable
    assert "memory_search_tool" not in stable


def test_format_returns_no_block_when_the_budget_fits_no_item():
    """One value larger than the whole budget leaves nothing to render: no block and no accepted items."""
    block = _format_memory_context({"working_state": "w" * 20000})
    assert block.text is None
    assert block.budget_used_chars == 0
    assert block.rules_injected == 0


# ---------------------------------------------------------------------------
# _format_memory_context — static context
# ---------------------------------------------------------------------------


def test_format_empty_returns_cold_start():
    """Empty context produces cold start guidance."""
    block = _format_memory_context({})
    stable = block.text
    assert stable == _COLD_START_CONTEXT
    assert block.budget_used_chars == 0
    assert "Discovery Mode" in stable
    assert MEMORY_CONTEXT_MARKER in stable
    assert "conversation_search" not in stable

    stable2 = _format_memory_context({"global_profile": {}, "rules": [], "agent_instructions": []}).text
    assert stable2 == _COLD_START_CONTEXT


def test_format_profile():
    ctx = {"global_profile": {"name": "Alice", "role": "Developer"}}
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert "# User Context (stable)" in stable
    assert "## Global User Profile" in stable
    assert "name: Alice" in stable
    assert "role: Developer" in stable


def test_format_instructions():
    ctx = {
        "agent_instructions": [
            {"instruction": "Always be concise"},
            {"instruction": "Use Python for examples"},
        ],
    }
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert "## Your Self-Instructions" in stable
    assert "Always be concise" in stable
    assert "Use Python for examples" in stable


def test_format_rules():
    ctx = {
        "rules": [
            {"trigger": "user asks for help", "action": "provide examples"},
            {"trigger": "error occurs", "action": "log and retry"},
        ],
    }
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert "## Behavioral Rules" in stable
    assert "When: user asks for help → Do: provide examples" in stable
    assert "When: error occurs → Do: log and retry" in stable


def test_format_complete_static():
    ctx = {
        "global_profile": {"name": "Bob"},
        "agent_instructions": [{"instruction": "Be helpful"}],
        "rules": [{"trigger": "greeting", "action": "respond warmly"}],
    }
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert "# User Context (stable)" in stable
    assert "## Global User Profile" in stable
    assert "## Your Self-Instructions" in stable
    assert "## Behavioral Rules" in stable
    assert "<user_memory_context>" in stable
    assert "</user_memory_context>" in stable


def test_format_includes_guidance_tail_once():
    """A warm block must carry Citation Requirements + Memory Search guidance.

    Without this tail, warm users with stored profile/rules would never be told to emit
    <cite:MEMORY_ID> tags, silently disabling the LLM-side citation channel that cold-start
    users do get.
    """
    ctx = {"global_profile": {"name": "Alice"}}
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert stable.count("## Citation Requirements") == 1
    assert "<cite:MEMORY_ID>" in stable
    assert "## Memory Search" in stable
    assert "memory_search_tool" in stable
    assert "corpus=" not in stable


def test_format_omits_guidance_when_tool_not_bound():
    """CONTEXT warm injection must not carry citation/search guidance (no bound tools)."""
    ctx = {"global_profile": {"name": "Alice"}}
    stable = _format_memory_context(ctx, memory_search_enabled=False).text
    assert stable is not None
    assert "## Citation Requirements" not in stable
    assert "<cite:MEMORY_ID>" not in stable
    assert "## Memory Search" not in stable
    assert "memory_search_tool" not in stable


def test_format_cold_start_context_mode_no_injection():
    """CONTEXT cold-start must not inject learning guidance (no memory tools bound)."""
    block = _format_memory_context({}, memory_search_enabled=False)
    assert block.text is None
    assert block.budget_used_chars == 0


def test_format_veto_negative_constraints():
    """VETO negative constraints are rendered into their own Priority 0 section."""
    ctx = {
        "rules": [
            {
                "id": "rule-normal",
                "trigger": "code commit",
                "action": "run linter",
            },
            {
                "id": "rule-veto-1",
                "is_veto": True,
                "tool_name": "bash_tool",
                "action": "rm -rf /",
                "reasoning": "Prevent system destruction",
                "application": "Use safe remove",
                "priority": 10,
            },
            {
                "id": "rule-veto-2",
                "trigger": "type annotation",
                "action": "never use Any type",
                "reasoning": "Strict type safety",
            },
        ]
    }
    stable = _format_memory_context(ctx).text
    assert stable is not None
    assert "## Mandatory Negative Constraints (VETO Rules)" in stable
    assert "[NEVER] rm -rf / (Scope: bash_tool)" in stable
    assert "Prevent system destruction" in stable
    assert "[NEVER] never use Any type" in stable

    # Normal rule stays in Behavioral Rules
    assert "## Behavioral Rules" in stable
    assert "When: code commit → Do: run linter" in stable
    assert "[NEVER] run linter" not in stable


def test_veto_section_lines_are_byte_stable_and_ordered():
    """Veto lines keep an exact wording and a (priority desc, id asc) order: they sit in the cached prompt prefix."""
    ctx = {
        "rules": [
            {"id": "b-low", "action": "never push to main", "reasoning": "protected branch"},
            {"id": "a-low", "action": "do not touch .env", "tool_name": "write_file", "priority": 0},
            {"id": "z-high", "action": "Never use sudo", "priority": 7},
        ]
    }
    stable = _format_memory_context(ctx).text
    assert stable is not None
    veto_lines = [line for line in stable.splitlines() if line.lstrip("- ").startswith("[NEVER]")]
    assert [line.lstrip("- ") for line in veto_lines] == [
        "[NEVER] Never use sudo (Scope: *)",
        "[NEVER] do not touch .env (Scope: write_file)",
        "[NEVER] never push to main (Scope: *) — Reason: protected branch",
    ]


class TestScopeBoundary:
    """Scope boundary declaration in <user_memory_context>."""

    def test_scope_boundary_present_when_stable_body_exists(self):
        ctx = {"global_profile": {"name": "Alice"}}
        stable = _format_memory_context(ctx).text
        assert stable is not None
        assert "Scope Boundary" in stable
        assert "Agent instructions ALWAYS take precedence" in stable
        assert "<user_instructions>" in stable

    def test_scope_boundary_appears_before_user_context_header(self):
        ctx = {"global_profile": {"name": "Bob"}}
        stable = _format_memory_context(ctx).text
        assert stable is not None
        sb_idx = stable.index("Scope Boundary")
        uc_idx = stable.index("# User Context (stable)")
        assert sb_idx < uc_idx

    def test_scope_boundary_absent_in_cold_start(self):
        stable = _format_memory_context({}).text
        assert stable is not None
        assert "Scope Boundary" not in stable
        assert "Discovery Mode" in stable

    def test_scope_boundary_is_blockquote_format(self):
        ctx = {"global_profile": {"name": "Dave"}}
        stable = _format_memory_context(ctx).text
        assert stable is not None
        assert "> **Scope Boundary**:" in stable


# ---------------------------------------------------------------------------
# _format_memory_context — the sections besides profile, rules and the scope boundary
# ---------------------------------------------------------------------------


class TestFormatRemainingSections:
    def test_memory_search_guidance_disabled_returns_empty(self):
        from myrm_agent_harness.agent.middlewares.memory_context.memory_context_format import (
            _memory_search_guidance,
        )

        assert _memory_search_guidance(memory_search_enabled=False) == ""

    def test_working_state_branch(self):
        ctx = {"working_state": "mid-task: drafting the migration plan"}
        stable = _format_memory_context(ctx).text
        assert stable is not None
        assert "Active Working Context" in stable
        assert "mid-task: drafting the migration plan" in stable

    def test_peer_profile_branch(self):
        ctx = {"peer_profile": {"tone": "friendly mentor", "name": "Alice"}}
        stable = _format_memory_context(ctx).text
        assert stable is not None
        assert "Our Relationship & Your Persona" in stable
        assert "tone: friendly mentor" in stable
        assert "name: Alice" in stable

    def test_knowledge_pack_never_enters_the_head_memory_block(self):
        """The pack changes per question; in the head block it would break the cached history prefix."""
        pack = {"snippets": [{"kb_name": "Finance", "article_title": "ExpensePolicy", "snippet": "capped at 650 RMB"}]}
        with_pack = {"global_profile": {"name": "Ada"}, "proactive_knowledge_pack": pack}

        block = _format_memory_context(with_pack)

        assert block == _format_memory_context({"global_profile": {"name": "Ada"}})
        assert "650 RMB" not in (block.text or "")

    def test_tool_guidance_injection(self):
        """Verify tool guidance is properly injected into stable sections."""
        ctx = {
            "tool_guidance": {
                "bash_tool": ["Do not use interactive shells", "Prefer ripgrep over grep"],
                "file_edit": ["Always read before write"],
            }
        }
        stable = _format_memory_context(ctx).text
        assert stable is not None
        assert "Tool Execution Guidance" in stable
        assert "[bash_tool] Do not use interactive shells" in stable
        assert "[file_edit] Always read before write" in stable
