"""Architecture gate: the default Turn-1 tool set stays under a ceiling measured on the wire.

``test_prompt_token_budget_gate`` budgets tool descriptions plus a flat per-tool wrapper, which leaves the
parameter schemas (about a third of what a provider is charged) unguarded. This gate counts what
``tool_bind_kwargs`` actually hands to the provider for the same default tool set: the converted,
provider-normalized function payload of every tool as compact JSON. Growth in a description or in a
parameter schema both trip it.

Measured on a host-independent basis (the bash tool's live OS hint is swapped for its static description),
with ``gpt-5`` as the normalization target; other model families normalize to within 0.3% of it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest
from langchain_core.tools import BaseTool

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "src"))

from myrm_agent_harness.agent.meta_tools.bash._tool.tool_description import (
    resolve_bash_code_execute_tool_description,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.binding import tool_bind_kwargs
from myrm_agent_harness.utils.text_utils import get_token_count
from myrm_agent_harness.utils.token_estimation import estimate_tools_schema_tokens

_WIRE_MODEL_ID = "gpt-5"
_BASH_TOOL_NAME = "bash_code_execute_tool"

# Default Turn-1 wire measured at 8,062 tokens (host-independent); the ceiling leaves ~2% headroom.
_MAX_WIRE_TOKENS = 8_230

# The total ceiling lets one tool balloon while another shrinks, so each tool also has its own. A tool that is not
# listed must stay under the default; a heavy tool declares a ceiling about 4% above its measured size and raises
# it deliberately when it has to grow.
_DEFAULT_TOOL_MAX_WIRE_TOKENS = 500
_HEAVY_TOOL_MAX_WIRE_TOKENS: dict[str, int] = {
    "bash_code_execute_tool": 1_850,
    "web_search_tool": 1_390,
    "memory_save_tool": 850,
    "file_read_tool": 830,
    "bash_process_tool": 590,
}

# The budgeter must not materially under-count what is sent; being conservative is allowed.
_MIN_ESTIMATOR_TO_WIRE_RATIO = 0.95


def _bound_function_payloads(tools: Sequence[BaseTool]) -> list[dict[str, object]]:
    """Function payloads exactly as ``tool_bind_kwargs`` binds them for a cloud OpenAI-compatible model."""
    bound = tool_bind_kwargs(
        tools,
        model_id=_WIRE_MODEL_ID,
        api_base="",
        custom_llm_provider="openai",
        tool_choice=None,
        parallel_tool_calls=None,
        extra={},
    )
    wire_tools = cast(list[dict[str, dict[str, object]]], bound["tools"])
    return [wire_tool["function"] for wire_tool in wire_tools]


def _payload_tokens(payload: dict[str, object]) -> int:
    return get_token_count(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _host_independent_tool_tokens(tools: Sequence[BaseTool]) -> dict[str, int]:
    """Wire tokens per tool, with the bash tool's live OS hint swapped for its static description."""
    per_tool = {str(payload["name"]): _payload_tokens(payload) for payload in _bound_function_payloads(tools)}
    bash_live = next(get_token_count(tool.description or "") for tool in tools if tool.name == _BASH_TOOL_NAME)
    bash_static = get_token_count(resolve_bash_code_execute_tool_description("en"))
    per_tool[_BASH_TOOL_NAME] += bash_static - bash_live
    return per_tool


@pytest.mark.architecture
class TestToolWireBudgetGate:
    """Wire-level token invariants for the default Turn-1 tool set."""

    @pytest.mark.asyncio
    async def test_default_tools_bind_completely(self) -> None:
        """A tool that fails conversion is skipped with a warning, which would hide its cost from the gate."""
        from scripts.measure_turn1_token_inventory import _build_default_turn1_tools

        tools = await _build_default_turn1_tools()
        bound_names = {str(payload["name"]) for payload in _bound_function_payloads(tools)}

        assert bound_names == {tool.name for tool in tools}

    @pytest.mark.asyncio
    async def test_turn1_default_tools_wire_token_budget(self) -> None:
        """Descriptions plus parameter schemas of the default tools stay under the wire ceiling."""
        from scripts.measure_turn1_token_inventory import _build_default_turn1_tools

        per_tool = _host_independent_tool_tokens(await _build_default_turn1_tools())

        budgeted_tokens = sum(per_tool.values())
        breakdown = ", ".join(f"{name}={tokens}" for name, tokens in sorted(per_tool.items(), key=lambda kv: -kv[1]))
        assert budgeted_tokens <= _MAX_WIRE_TOKENS, (
            f"Turn-1 default tools cost {budgeted_tokens} wire tokens, over the {_MAX_WIRE_TOKENS} ceiling "
            f"(host-independent basis: bash OS hint excluded). Per tool: {breakdown}"
        )

    @pytest.mark.asyncio
    async def test_no_single_tool_outgrows_its_wire_ceiling(self) -> None:
        """Each default tool stays under its own ceiling, and the ceiling table lists only tools that need one."""
        from scripts.measure_turn1_token_inventory import _build_default_turn1_tools

        per_tool = _host_independent_tool_tokens(await _build_default_turn1_tools())

        over = {
            name: f"{tokens} > {_HEAVY_TOOL_MAX_WIRE_TOKENS.get(name, _DEFAULT_TOOL_MAX_WIRE_TOKENS)}"
            for name, tokens in per_tool.items()
            if tokens > _HEAVY_TOOL_MAX_WIRE_TOKENS.get(name, _DEFAULT_TOOL_MAX_WIRE_TOKENS)
        }
        assert not over, f"tools over their wire ceiling (raise it deliberately, or trim the tool): {over}"

        needless = {
            name for name in _HEAVY_TOOL_MAX_WIRE_TOKENS if per_tool.get(name, 0) <= _DEFAULT_TOOL_MAX_WIRE_TOKENS
        }
        assert not needless, f"ceiling entries for tools that are gone or fit the default ceiling: {sorted(needless)}"

    @pytest.mark.asyncio
    async def test_estimator_does_not_undercount_the_wire(self) -> None:
        """Context budgeting relies on the estimate being at least what the provider receives."""
        from scripts.measure_turn1_token_inventory import _build_default_turn1_tools

        tools = await _build_default_turn1_tools()
        wire_tokens = sum(_payload_tokens(payload) for payload in _bound_function_payloads(tools))
        estimated_tokens = estimate_tools_schema_tokens(tools)

        assert estimated_tokens >= wire_tokens * _MIN_ESTIMATOR_TO_WIRE_RATIO, (
            f"estimate_tools_schema_tokens counts {estimated_tokens} tokens for tools that cost "
            f"{wire_tokens} on the wire"
        )
