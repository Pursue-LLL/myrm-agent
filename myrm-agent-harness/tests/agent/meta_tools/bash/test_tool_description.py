"""Static bash tool description contract tests.

The description is one prompt per locale. These tests pin what the model must be told and where each fact has
its single owner (parameter limits in ``BashInput``, background job management in ``bash_process_tool``, the
read-back path of an evicted output in the eviction footer), not the wording around it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import get_os_hint
from myrm_agent_harness.agent.meta_tools.bash._tool.tool_description import (
    TOOL_DESCRIPTION_EN,
    TOOL_DESCRIPTION_ZH,
)
from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import (
    create_bash_code_execute_tool,
)
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
    create_bash_process_tool,
)

_PROCESS_ACTIONS = ("list", "output", "wait", "kill", "write_stdin", "submit_stdin", "close_stdin")
# Rules whose single owner is the bash_process_tool description (or its result fields).
_PROCESS_TOOL_RULES = ("waiting_for_input", "input_wait_hint", "since_cursor", "SIGTERM", "still_running")


@dataclass(frozen=True)
class _Locale:
    """The locale-specific words the contract tests look for."""

    text: str
    state_heading: str
    output_heading: str
    background_heading: str
    variable: str
    cannot_be_answered: str
    hedge: str
    promises: tuple[str, ...]
    to_a_file: str
    summaries: str
    background_scope: str


_EN = _Locale(
    text=TOOL_DESCRIPTION_EN,
    state_heading="State",
    output_heading="Output and Errors",
    background_heading="Background Tasks",
    variable="{variable}",
    cannot_be_answered="cannot be answered",
    hedge="not guaranteed",
    promises=("remain active", "persist"),
    to_a_file="write intermediate data to a file",
    summaries="summaries of large data",
    background_scope="background tasks",
)
_ZH = _Locale(
    text=TOOL_DESCRIPTION_ZH,
    state_heading="状态",
    output_heading="输出与错误",
    background_heading="后台任务",
    variable="{变量}",
    cannot_be_answered="无法应答",
    hedge="不保证",
    promises=("始终生效", "持久"),
    to_a_file="把中间数据写到文件",
    summaries="只给摘要",
    background_scope="后台长任务",
)
_BOTH = pytest.mark.parametrize("locale", [_EN, _ZH], ids=["en", "zh"])


def _line_starting_with(text: str, prefix: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(prefix))


def _capability(text: str, number: int) -> str:
    """The numbered capability item (its first line)."""
    return _line_starting_with(text, f"{number}. **")


def _section(text: str, heading: str) -> str:
    """Body of the ``## heading`` section, up to the next ``## `` heading."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert match, f"section {heading!r} missing"
    return match.group(1)


def _code_blocks(text: str) -> list[str]:
    return re.findall(r"```python\n(.*?)```", text, re.S)


def test_tool_description_module_exports() -> None:
    from myrm_agent_harness.agent.meta_tools.bash._tool import tool_description as mod

    assert "TOOL_DESCRIPTION_EN" in mod.__all__
    assert "TOOL_DESCRIPTION_ZH" in mod.__all__
    assert "resolve_bash_code_execute_tool_description" in mod.__all__


def test_create_bash_tool_static_description_only() -> None:
    bash_tool_default = create_bash_code_execute_tool()
    description_en = bash_tool_default.description

    assert description_en.startswith(TOOL_DESCRIPTION_EN)
    assert get_os_hint(locale="en") in description_en
    assert "## PTC" not in description_en
    assert "Turn1-bound tools" not in description_en
    assert "myrm_tools.web_search_tool" not in description_en
    assert "tools.session_store" not in description_en

    bash_tool_zh = create_bash_code_execute_tool(locale="zh-CN")
    description_zh = bash_tool_zh.description
    assert description_zh.startswith(TOOL_DESCRIPTION_ZH)
    assert get_os_hint(locale="zh-CN") in description_zh

    static_pos = description_zh.find("**Shell**")
    os_pos = description_zh.find(get_os_hint(locale="zh-CN").strip()[:20])
    assert 0 <= static_pos < os_pos
    assert description_zh == TOOL_DESCRIPTION_ZH + get_os_hint(locale="zh-CN")


def test_locales_carry_the_same_structure_and_the_same_entrypoint_example() -> None:
    """A fact added to one locale must reach the other: same sections, same four capabilities, same example code."""
    for text in (TOOL_DESCRIPTION_EN, TOOL_DESCRIPTION_ZH):
        assert re.findall(r"^(\d+)\. \*\*", text, re.M) == ["1", "2", "3", "4"]
    assert len(re.findall(r"^## ", TOOL_DESCRIPTION_EN, re.M)) == len(re.findall(r"^## ", TOOL_DESCRIPTION_ZH, re.M))
    assert _code_blocks(TOOL_DESCRIPTION_EN) == _code_blocks(TOOL_DESCRIPTION_ZH)


@_BOTH
def test_every_section_pointer_resolves(locale: _Locale) -> None:
    """A ``see "X"`` / ``见「X」`` pointer must name a heading that exists (no dangling cross reference)."""
    headings = {heading.strip() for heading in re.findall(r"^#{2,4} (.+)$", locale.text, re.M)}
    pointers = re.findall(r'see "([^"]+)"', locale.text) + re.findall(r"见「([^」]+)」", locale.text)
    assert [pointer for pointer in pointers if pointer not in headings] == []


@_BOTH
def test_native_tools_are_routed_by_name_and_bash_keeps_runtime_work(locale: _Locale) -> None:
    for name in ("file_read_tool", "file_write_tool", "file_edit_tool", "glob_tool", "grep_tool"):
        assert f"`{name}`" in locale.text
    assert "myrm_tools" not in locale.text
    scope = _line_starting_with(locale.text, "`bash_code_execute_tool`")
    for keyword in ("mv/cp/rm", "curl", locale.background_scope):
        assert keyword in scope


@_BOTH
def test_bash_description_is_decoupled_from_mcp_skill_sop(locale: _Locale) -> None:
    """MCP workflow belongs in Skill docs, not bash tool description."""
    for fragment in ("/mcp/", "skill_select_tool", "MCP Skill", "from skills.", "from tools.", "tools.session_store"):
        assert fragment not in locale.text


@_BOTH
def test_prompt_leaks_no_internal_impl_or_session_store(locale: _Locale) -> None:
    for fragment in ("session_load", "session_keys", "chat_id", "文件模式", "框架自动识别", "TS 类型", "TypeScript"):
        assert fragment not in locale.text


@_BOTH
def test_no_claim_about_the_default_working_directory(locale: _Locale) -> None:
    """The default directory differs per executor (a local shell does not start in ``/workspace``)."""
    assert "/workspace" not in locale.text


@_BOTH
def test_reason_and_limits_stay_in_the_parameter_schema(locale: _Locale) -> None:
    """``reason`` and the yield / background-job limits are owned by the ``BashInput`` field texts."""
    for fragment in ("≥10", "yield_after_seconds", "Max 5", "最多 5"):
        assert fragment not in locale.text


@_BOTH
def test_combining_steps_names_the_control_flow_the_model_can_use(locale: _Locale) -> None:
    combine = _capability(locale.text, 3)
    for keyword in ("`if`", "`while`", "`try`", "asyncio.gather", "`&&`", "`|`"):
        assert keyword in combine


def test_unknown_shapes_are_observed_in_the_same_block_not_split() -> None:
    """An unknown return shape must not force a second turn for independent or constructible calls."""
    en, zh = _capability(TOOL_DESCRIPTION_EN, 3), _capability(TOOL_DESCRIPTION_ZH, 3)
    assert "unknown return shape is NOT a reason to split" in en
    assert "print the real value as `[OBSERVATION]` and continue in the same block" in en
    assert "NEVER" in en and "seen documented or printed" in en
    assert "Split only when later arguments cannot be built" in en
    assert "返回结构不明确不是拆分的理由" in zh
    assert "在同一块打印真实值 `[OBSERVATION]` 后继续" in zh
    assert "严禁" in zh and "没打印过的字段" in zh
    assert "只有后续参数必须看到结果才能构造时才拆分" in zh


@_BOTH
def test_output_markers_are_defined_once_with_their_scope(locale: _Locale) -> None:
    """``[OBSERVATION]`` inspects, ``[RESULT]`` answers; the print forms are specified in one place only."""
    section = _section(locale.text, locale.output_heading)
    observation = f'print(f"[OBSERVATION] {locale.variable}")'
    assert locale.text.count(observation) == 1
    assert observation in section
    assert section.count("[RESULT]") == 1
    assert locale.summaries in section


@_BOTH
def test_entrypoint_example_is_the_gather_then_observe_then_result_shape(locale: _Locale) -> None:
    (code,) = _code_blocks(locale.text)
    assert code.index("asyncio.gather") < code.index("[OBSERVATION]") < code.index("[RESULT]")
    assert "asyncio.run(main())" in code
    assert "# only if constructible" in code
    for fragment in ("lookup_codes", "BJP", "func_a(...)"):
        assert fragment not in code
    assert "await" in _capability(locale.text, 4)


def test_failure_handling_asks_for_the_root_cause_not_a_blind_rerun() -> None:
    assert "stderr" in TOOL_DESCRIPTION_EN
    assert "never rerun the same command unchanged" in TOOL_DESCRIPTION_EN
    assert "stderr" in TOOL_DESCRIPTION_ZH
    assert "定位根因" in TOOL_DESCRIPTION_ZH
    assert "严禁**原样重跑同一命令" in TOOL_DESCRIPTION_ZH


@_BOTH
def test_state_section_makes_no_promise_about_shell_state_across_calls(locale: _Locale) -> None:
    """Each call is a fresh start (``test_product_path_state``): the text hedges and names the combined-call way out."""
    state = _section(locale.text, locale.state_heading)
    assert locale.hedge in state
    assert "cd" in state
    assert "export" in state
    assert not [promise for promise in locale.promises if promise in state.lower()]
    assert locale.to_a_file in state


@_BOTH
def test_shell_capability_says_a_foreground_prompt_cannot_be_answered_and_names_the_way_out(locale: _Locale) -> None:
    """The text states the outcome the model sees, not how input is isolated (that differs per shell), and routes
    a program that must be answered through a background job (``test_product_path_stdin`` covers the behavior)."""
    capability = _capability(locale.text, 1)
    assert locale.cannot_be_answered in capability
    assert "stdin" not in capability
    assert "EOF" not in capability
    assert "run_in_background" in capability
    assert "bash_process_tool" in capability


@_BOTH
def test_background_section_keeps_only_the_progress_markers(locale: _Locale) -> None:
    """The action list and the input-wait contract belong to ``bash_process_tool``; here only what the script prints."""
    section = _section(locale.text, locale.background_heading)
    assert "MYRM_PROGRESS" in section
    assert "MYRM_CHECKPOINT" in section
    assert [rule for rule in _PROCESS_TOOL_RULES if rule in locale.text] == []
    assert [action for action in ("write_stdin", "submit_stdin", "close_stdin") if action in locale.text] == []


def test_process_tool_description_owns_the_background_job_contract() -> None:
    process_desc = create_bash_process_tool().description or ""
    for action in _PROCESS_ACTIONS:
        assert action in process_desc
    for rule in ("waiting_for_input", "input_wait_hint", "submit_stdin", "since_cursor"):
        assert rule in process_desc


def test_bash_process_tool_description_documents_waiting_for_input() -> None:
    tool = create_bash_process_tool()
    desc = tool.description or ""
    assert "waiting_for_input" in desc
    assert "input_wait_hint" in desc
    assert "submit_stdin" in desc
    assert "blind-poll" in desc


def test_bash_process_pid_field_guides_integer_type() -> None:
    """pid must be an integer — a string job id triggers schema ValidationError."""
    from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import (
        _BashProcessInput,
    )

    pid_desc = _BashProcessInput.model_fields["pid"].description or ""
    assert "do not pass a string" in pid_desc
    json_schema = _BashProcessInput.model_json_schema()
    types = {t.get("type") for t in json_schema["properties"]["pid"].get("anyOf", [])}
    assert "integer" in types
