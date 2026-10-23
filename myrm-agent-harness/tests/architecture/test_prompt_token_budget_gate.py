"""Architecture gate: harness-level prompt rule budget and Turn-1 tool inventory.

Validates (harness scope — 3 checks):
1. Turn-1 default tool profile token overhead (CORE + HIGH_PRIORITY descriptions
   + schema wrappers) does NOT exceed ceiling (≤6500 tokens), measured on a
   host-independent basis: the bash tool's live OS hint is swapped for its static
   description, and the hint is capped separately so a host quirk cannot decide the verdict.
2. Harness system rule constants stay compact: AGENT_CORE_RULES ≤350,
   SECURITY_BOUNDARY_SYSTEM_RULES ≤350, DATETIME_SYSTEM_RULES ≤120.
3. SystemMessage content hash is immutable across multiple resolutions
   (prompt cache safety).

Business-layer CORE prompt caps (full ≤2000 / lean ≤1200 / lean÷full ≤0.70 on
``cl100k_base``) live in the server repo:
``myrm-agent-server/tests/ai_agents/test_prompt_integrity.py::TestPromptTokenBudgetGate``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "src"))

from myrm_agent_harness.agent.streaming.model_discipline import (
    AGENT_CORE_RULES,
)
from myrm_agent_harness.agent.streaming.utils import (
    DATETIME_SYSTEM_RULES,
)
from myrm_agent_harness.core.security.detection.content_boundary import (
    SECURITY_BOUNDARY_SYSTEM_RULES,
)
from myrm_agent_harness.utils.text_utils import get_token_count
from myrm_agent_harness.utils.token_estimation import (
    estimate_tool_descriptions_tokens,
)


@pytest.mark.architecture
class TestPromptTokenBudgetGate:
    """CI gate enforcing prompt token budget invariants and prompt cache invariants."""

    @pytest.mark.asyncio
    async def test_turn1_default_tools_token_budget(self) -> None:
        """Turn-1 default tools stay under the ceiling on any host.

        The bash tool's description is ``static + get_os_hint()``, and the hint states the host OS
        and whatever the Python toolchain probe can reach: 58 tokens on this macOS arm64 box, 32 on
        ubuntu-latest, 31-60 across distributions, and up to ~100 when a probe finds an unusual
        interpreter mix. Charging that live number would let the gate flip on a PATH or a probe
        outcome instead of on an edit, so the budget compares the host-independent description
        total and the hint is checked against its own allowance.

        Scope is description + wrapper only — tool parameter schemas are tracked separately in
        DEFAULT_AGENT_TOKEN_INVENTORY.md §六.
        """
        from scripts.measure_turn1_token_inventory import _build_default_turn1_tools

        from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import get_os_hint
        from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
            resolve_bash_code_execute_tool_description,
        )

        # Widest hint seen in practice is ~100 tokens; 120 leaves room without hiding a real blowup.
        os_hint_allowance = 120
        live_hint = get_token_count(get_os_hint("en"))
        assert live_hint <= os_hint_allowance, (
            f"bash OS hint grew to {live_hint} tokens, past the {os_hint_allowance}-token allowance "
            "the Turn-1 tool budget assumes for it"
        )

        tools = await _build_default_turn1_tools()
        bash_static = get_token_count(resolve_bash_code_execute_tool_description("en"))
        bash_live = next(
            get_token_count(tool.description or "") for tool in tools if tool.name == "bash_code_execute_tool"
        )
        # Substitute the static half for the live description: identical on every host.
        budgeted_tokens = estimate_tool_descriptions_tokens(tools) - bash_live + bash_static

        max_allowed_tools_tokens = 6500
        assert budgeted_tokens <= max_allowed_tools_tokens, (
            f"Turn-1 default tool descriptions cost {budgeted_tokens} tokens, over the "
            f"{max_allowed_tools_tokens} ceiling (host-independent basis: bash hint excluded, "
            f"wrapper included; live hint was {live_hint})"
        )

    def test_harness_system_prompt_rules_budget(self) -> None:
        """Assert that harness core behavior, security boundary, and datetime rules remain compact."""
        agent_core_tokens = get_token_count(AGENT_CORE_RULES)
        sec_boundary_tokens = get_token_count(SECURITY_BOUNDARY_SYSTEM_RULES)
        datetime_tokens = get_token_count(DATETIME_SYSTEM_RULES)

        # AGENT_CORE_RULES baseline ~240 tokens, ceiling 350 tokens
        assert (
            agent_core_tokens <= 350
        ), f"AGENT_CORE_RULES tokens {agent_core_tokens} exceeded ceiling 350"

        # SECURITY_BOUNDARY_SYSTEM_RULES baseline ~257 tokens, ceiling 350 tokens
        assert (
            sec_boundary_tokens <= 350
        ), f"SECURITY_BOUNDARY_SYSTEM_RULES tokens {sec_boundary_tokens} exceeded ceiling 350"

        # DATETIME_SYSTEM_RULES baseline ~70 tokens, ceiling 120 tokens
        assert (
            datetime_tokens <= 120
        ), f"DATETIME_SYSTEM_RULES tokens {datetime_tokens} exceeded ceiling 120"

    def test_harness_rules_byte_and_hash_stability(self) -> None:
        """Assert that harness system rules are immutable string constants preserving KV cache."""
        from langchain_core.messages import SystemMessage

        from myrm_agent_harness.agent.context_management.infra.cache_break_detector import (
            _compute_system_prompt_hash,
        )

        msg1 = [
            SystemMessage(content=AGENT_CORE_RULES),
            SystemMessage(content=SECURITY_BOUNDARY_SYSTEM_RULES),
            SystemMessage(content=DATETIME_SYSTEM_RULES),
        ]
        msg2 = [
            SystemMessage(content=AGENT_CORE_RULES),
            SystemMessage(content=SECURITY_BOUNDARY_SYSTEM_RULES),
            SystemMessage(content=DATETIME_SYSTEM_RULES),
        ]

        h1 = _compute_system_prompt_hash(msg1)
        h2 = _compute_system_prompt_hash(msg2)
        assert h1 == h2, "System rule hash must be strictly deterministic across calls"
        assert len(h1) == 64
