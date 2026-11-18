"""Static bash tool description prompt hygiene tests."""

from __future__ import annotations

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

    static_pos = description_zh.find("**Shell 命令**")
    os_pos = description_zh.find(get_os_hint(locale="zh-CN").strip()[:20])
    assert 0 <= static_pos < os_pos
    assert description_zh == TOOL_DESCRIPTION_ZH + get_os_hint(locale="zh-CN")


def test_native_tool_priority_section_still_directs_single_calls() -> None:
    assert "`file_read_tool`" in TOOL_DESCRIPTION_ZH
    assert "`glob_tool`" in TOOL_DESCRIPTION_ZH
    assert "`grep_tool`" in TOOL_DESCRIPTION_ZH
    assert "myrm_tools.grep_tool" not in TOOL_DESCRIPTION_ZH


def test_bash_description_is_decoupled_from_mcp_skill_sop() -> None:
    """MCP workflow belongs in Skill docs, not bash tool description."""
    assert "/mcp/" not in TOOL_DESCRIPTION_ZH
    assert "skill_select_tool" not in TOOL_DESCRIPTION_ZH
    assert "MCP Skill" not in TOOL_DESCRIPTION_ZH
    assert "from skills." not in TOOL_DESCRIPTION_ZH
    assert "from tools." not in TOOL_DESCRIPTION_ZH
    assert "tools.session_store" not in TOOL_DESCRIPTION_ZH


def test_large_output_eviction_read_hint_documented() -> None:
    assert "file_read_tool" in TOOL_DESCRIPTION_ZH
    assert ".context/.../evicted/" in TOOL_DESCRIPTION_ZH


def test_failure_root_cause_guidance_documented() -> None:
    """失败处理引导：先读 stderr/错误提示定位根因，勿盲目重试同一命令."""
    assert "stderr" in TOOL_DESCRIPTION_ZH
    assert "盲目重试" in TOOL_DESCRIPTION_ZH
    assert "定位根因" in TOOL_DESCRIPTION_ZH
    assert "严禁在未调整参数或逻辑时连续重复执行" in TOOL_DESCRIPTION_ZH


def test_optimization_strategy_merge_control_flow_documented() -> None:
    """L74: Python 源码合并 + 控制流，避免与专用工具优先歧义的旧表述."""
    assert "多次操作合并进一次 Python 源码" in TOOL_DESCRIPTION_ZH
    assert "while/if/try" in TOOL_DESCRIPTION_ZH
    assert "避免多次往返调用" in TOOL_DESCRIPTION_ZH
    assert "替代多次工具调用" not in TOOL_DESCRIPTION_ZH
    assert "无需压缩或转义" in TOOL_DESCRIPTION_ZH


def test_optimization_strategy_output_summary_documented() -> None:
    """L75: 大数据用 Python 分析，只给摘要."""
    assert "只输出所需数据" in TOOL_DESCRIPTION_ZH
    assert "只给摘要" in TOOL_DESCRIPTION_ZH
    assert "CSV/JSON/日志" in TOOL_DESCRIPTION_ZH


def test_unknown_shapes_can_be_observed_without_splitting() -> None:
    """Unknown shape must not force a second turn for independent/constructible calls."""
    assert "unknown return shape is NOT a reason to split" in TOOL_DESCRIPTION_EN
    assert "返回结构不明确不是拆分的理由" in TOOL_DESCRIPTION_ZH
    assert "同一块打印" in TOOL_DESCRIPTION_ZH
    assert "print the real value as `[OBSERVATION]`" in TOOL_DESCRIPTION_EN
    assert TOOL_DESCRIPTION_ZH.count('`print(f"[OBSERVATION] {变量}")`') == 1


def test_merge_rules_and_output_format_documented() -> None:
    assert "asyncio.gather" in TOOL_DESCRIPTION_ZH
    assert "[OBSERVATION]" in TOOL_DESCRIPTION_ZH
    assert "[RESULT]" in TOOL_DESCRIPTION_ZH
    assert "file_write_tool" in TOOL_DESCRIPTION_ZH
    assert "func_a(...)" not in TOOL_DESCRIPTION_ZH
    assert "lookup_codes" not in TOOL_DESCRIPTION_ZH
    assert "BJP" not in TOOL_DESCRIPTION_ZH


def test_cross_call_persistence_uses_workspace_files_not_session_store() -> None:
    assert "tools.session_store" not in TOOL_DESCRIPTION_ZH
    assert "session_load" not in TOOL_DESCRIPTION_ZH
    assert "session_keys" not in TOOL_DESCRIPTION_ZH
    assert "json.dump" in TOOL_DESCRIPTION_ZH or "json.dump/load" in TOOL_DESCRIPTION_ZH
    assert "file_write_tool" in TOOL_DESCRIPTION_ZH
    assert "禁止" in TOOL_DESCRIPTION_ZH and "[RESULT]" in TOOL_DESCRIPTION_ZH
    assert "优先合并到单次代码执行中" in TOOL_DESCRIPTION_ZH
    assert "Prefer combining operations into a single execution" in TOOL_DESCRIPTION_EN
    assert "chat_id" not in TOOL_DESCRIPTION_ZH
    assert "chat_id" not in TOOL_DESCRIPTION_EN


def test_no_internal_module_name_leaked_to_prompt() -> None:
    """内部模块名 myrm_tools 不得泄漏进 prompt（此地无银反模式）."""
    assert "myrm_tools" not in TOOL_DESCRIPTION_ZH


def test_background_contract_documented() -> None:
    assert "run_in_background=true" in TOOL_DESCRIPTION_ZH
    assert "since_cursor" not in TOOL_DESCRIPTION_ZH
    assert "waiting_for_input" in TOOL_DESCRIPTION_ZH
    assert "input_wait_hint" in TOOL_DESCRIPTION_ZH
    assert TOOL_DESCRIPTION_ZH.count("waiting_for_input") >= 2
    assert "MYRM_PROGRESS" in TOOL_DESCRIPTION_ZH
    assert "MYRM_CHECKPOINT" in TOOL_DESCRIPTION_ZH
    assert "bash_process_tool" in TOOL_DESCRIPTION_ZH
    assert "write_stdin" in TOOL_DESCRIPTION_ZH
    assert "submit_stdin" in TOOL_DESCRIPTION_ZH
    assert "close_stdin" in TOOL_DESCRIPTION_ZH
    assert "SIGTERM" not in TOOL_DESCRIPTION_ZH
    assert "still_running" not in TOOL_DESCRIPTION_ZH


def test_background_detail_authority_lives_in_process_tool_desc() -> None:
    """后台 action 细节只维护在 bash_process_tool 自身 desc,TOOL_DESCRIPTION_ZH 仅概要预告."""
    process_desc = create_bash_process_tool().description or ""
    assert "list" in process_desc
    assert "kill" in process_desc
    assert "close_stdin" in process_desc
    assert "详见其工具描述" in TOOL_DESCRIPTION_ZH


def test_glob_routing_omits_nonexistent_depth_argument() -> None:
    assert "glob_tool" in TOOL_DESCRIPTION_ZH
    assert "限定 depth" not in TOOL_DESCRIPTION_ZH
    assert 'pattern="*"' not in TOOL_DESCRIPTION_ZH


def test_native_tool_routing_defers_usage_to_tool_descriptions() -> None:
    assert "检索代码" not in TOOL_DESCRIPTION_ZH
    assert "参数与示例见各工具描述" in TOOL_DESCRIPTION_ZH


def test_bash_positive_routing_covers_runtime_ops() -> None:
    routing = TOOL_DESCRIPTION_ZH.split("## 编写原则", maxsplit=1)[0]
    assert "curl" in routing
    assert "后台长任务" in routing
    assert "读文件/搜内容/列目录用上节专用工具" in routing


def test_preinstalled_third_party_libs_listed() -> None:
    assert "pandas" in TOOL_DESCRIPTION_ZH
    assert "numpy" in TOOL_DESCRIPTION_ZH


def test_workspace_path_hint_documented() -> None:
    assert "/workspace/..." in TOOL_DESCRIPTION_ZH


def test_python_c_wrapper_discouraged() -> None:
    assert "python -c" in TOOL_DESCRIPTION_ZH
    assert "python script.py" in TOOL_DESCRIPTION_ZH


def test_prompt_leaks_no_internal_impl_or_cross_language_schema() -> None:
    assert "文件模式" not in TOOL_DESCRIPTION_ZH
    assert "框架自动识别" not in TOOL_DESCRIPTION_ZH
    assert "TS 类型" not in TOOL_DESCRIPTION_ZH
    assert "TS类型" not in TOOL_DESCRIPTION_ZH
    assert "TypeScript" not in TOOL_DESCRIPTION_ZH


def test_capabilities_section_documents_combo_modes() -> None:
    """能力段枚举管道/组合形态; merge/OBSERVATION 判定细则只在编写原则."""
    capabilities_end = TOOL_DESCRIPTION_ZH.index("## 优先使用专用工具")
    capabilities = TOOL_DESCRIPTION_ZH[:capabilities_end]
    assert "组合执行" in capabilities
    assert "管道思想" in capabilities
    assert "技能批量" in capabilities
    assert "`&&`" in capabilities
    assert "`|`" in capabilities
    assert "见 #2" in capabilities
    assert "编写原则" in capabilities
    assert "多轮 Shell 持久" not in capabilities
    assert capabilities.count("依赖性分析") == 0
    assert "asyncio.gather" not in capabilities
    assert "判定标准" not in capabilities
    assert "组合调用能力或方法以提效" not in capabilities
    assert "组合调用工具或方法以提效" not in capabilities


def test_async_section_documents_why_and_links_to_gather_examples() -> None:
    assert "技能/MCP 调用为 async" in TOOL_DESCRIPTION_ZH
    assert "必须 await" in TOOL_DESCRIPTION_ZH
    assert "写法见上方示例" in TOOL_DESCRIPTION_ZH


def test_shell_commands_include_common_ops() -> None:
    assert "mv/cp/rm" in TOOL_DESCRIPTION_ZH


def test_reason_not_duplicated_in_static_prompt() -> None:
    """reason lives in BashInput schema, not static TOOL_DESCRIPTION_ZH."""
    assert "≥10" not in TOOL_DESCRIPTION_ZH


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


def test_bash_process_and_execute_prompts_share_stdin_contract() -> None:
    process_desc = create_bash_process_tool().description or ""
    for keyword in ("waiting_for_input", "input_wait_hint", "submit_stdin"):
        assert keyword in TOOL_DESCRIPTION_ZH
        assert keyword in process_desc


def _line_starting_with(text: str, prefix: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(prefix))


def test_shell_capability_says_a_foreground_prompt_cannot_be_answered_and_names_the_way_out() -> None:
    """The text states the outcome the model sees, not how input is isolated (that differs per shell), and routes
    a program that must be answered through a background job (``test_product_path_stdin`` covers the behavior)."""
    for text, cannot_be_answered in (
        (TOOL_DESCRIPTION_EN, "cannot be answered"),
        (TOOL_DESCRIPTION_ZH, "无法应答"),
    ):
        capability = _line_starting_with(text, "1. ")
        assert cannot_be_answered in capability
        assert "stdin" not in capability
        assert "EOF" not in capability
        assert "run_in_background" in capability
        assert "bash_process_tool" in capability


def test_state_section_makes_no_promise_about_shell_state_across_calls() -> None:
    """Each call is a fresh start (``test_product_path_state``): the text hedges and names the combined-call way out."""
    for text, hedge, promises in (
        (TOOL_DESCRIPTION_EN, "not guaranteed", ("remain active", "persist")),
        (TOOL_DESCRIPTION_ZH, "不保证", ("始终生效", "持久")),
    ):
        bash_state = _line_starting_with(text, "- **Bash**")
        assert hedge in bash_state
        assert "cd" in bash_state
        assert "export" in bash_state
        assert not [promise for promise in promises if promise in bash_state.lower()]
