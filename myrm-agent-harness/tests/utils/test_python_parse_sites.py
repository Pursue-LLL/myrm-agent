"""Every gate that reads Python text answers text the parser cannot take with its own refusal and never raises.

The text comes from a model, a skill file or a tool argument, so what fails the parser is its author's choice: a lone
surrogate (JSON allows one), a unary chain that exhausts the parser's stack, an expression chained past its recursion
limit. A gate that raises on it fails on every call of that text, and a handler further out can turn the crash into a
permissive default. Each test pins the answer a gate gives: no PTC intent, not read-only, hollow, a fatal lint issue,
a refusal, the text left as it was.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.dynamic_workflow.linter import lint_workflow_script
from myrm_agent_harness.agent.dynamic_workflow.template_validation import script_all_spawns_readonly
from myrm_agent_harness.agent.meta_tools.bash._security.preflight_checks import check_myrm_tools_import
from myrm_agent_harness.agent.security.ptc_verifier import extract_ptc_intent
from myrm_agent_harness.agent.skills.evolution.core.eval_regression import _check_imports, _run_single_case
from myrm_agent_harness.agent.skills.evolution.execution.hollow_detector import HollowTestDetector
from myrm_agent_harness.toolkits.code_execution.python_extractor import detect_ptc_imports, validate_python_syntax
from myrm_agent_harness.toolkits.mcp.schema.coerce import coerce_value

LONE_SURROGATE = "x = '\ud800'"
PARSER_STACK_OVERFLOW = "x = " + "-" * 20_000 + "1"
RECURSION_LIMIT = "x = " + " + ".join(["1"] * 30_000)
# Parses, but a recursive walk over its tree passes the interpreter's recursion limit.
WALK_OVERFLOW = "x = " + " + ".join(["1"] * 3_000)

UNPARSEABLE = pytest.mark.parametrize(
    "text",
    [LONE_SURROGATE, PARSER_STACK_OVERFLOW, RECURSION_LIMIT],
    ids=["lone-surrogate", "parser-stack-overflow", "recursion-limit"],
)
UNANALYSABLE = pytest.mark.parametrize(
    "text",
    [LONE_SURROGATE, PARSER_STACK_OVERFLOW, RECURSION_LIMIT, WALK_OVERFLOW],
    ids=["lone-surrogate", "parser-stack-overflow", "recursion-limit", "walk-overflow"],
)


@UNPARSEABLE
def test_ptc_verifier_extracts_no_intent_from_text_it_cannot_parse(text: str) -> None:
    skill_call = "from demo_skill import tool\ntool(path='a.txt')\n"

    assert extract_ptc_intent(f"python3 <<'EOF'\n{skill_call}EOF") == ("demo_skill", "tool", {"path": "a.txt"})
    assert extract_ptc_intent(f"python3 <<'EOF'\n{skill_call}{text}\nEOF") is None


@UNPARSEABLE
def test_myrm_tools_guard_lets_text_it_cannot_parse_pass(text: str) -> None:
    # The guard blocks by raising ToolError, so returning at all is the answer; the parser's own error must not leak.
    check_myrm_tools_import(f"python3 <<'EOF'\n{text}\nEOF")


@UNPARSEABLE
def test_a_script_the_parser_cannot_take_is_not_read_only(text: str) -> None:
    assert script_all_spawns_readonly(text) is False


@UNANALYSABLE
def test_linter_reports_a_script_it_cannot_analyse_as_one_fatal_issue(text: str) -> None:
    report = lint_workflow_script(text)

    assert not report.is_valid
    assert [(issue.issue_code, issue.line) for issue in report.issues] == [("SYNTAX_ERROR", None)]


@UNPARSEABLE
def test_unparseable_test_code_is_hollow(text: str) -> None:
    result = HollowTestDetector().analyze_python_code(text)

    assert result.is_hollow
    assert "cannot be parsed" in result.reasons[0]


@UNPARSEABLE
def test_eval_regression_fails_the_checks_of_unparseable_variant_code(text: str) -> None:
    assert _run_single_case({"sandbox_assertions": [{"type": "ast_valid"}]}, text) is False
    assert _check_imports(text, "os") is False


@UNPARSEABLE
def test_syntax_precheck_refuses_text_the_parser_cannot_take(text: str) -> None:
    error = validate_python_syntax(text)

    assert error is not None
    assert "cannot be parsed" in error
    assert detect_ptc_imports(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "{[1]: 2}",
        "{1: " + "-" * 20_000 + "1}",
        "{1: " + "+".join(["1"] * 20_000) + "}",
        "[" * 32_000 + "]" * 32_000,
    ],
    ids=["unhashable-key", "parser-stack-overflow", "recursion-limit", "json-nesting"],
)
def test_coerce_leaves_container_text_no_parser_can_take_as_it_was(text: str) -> None:
    assert coerce_value({"type": "object"}, text) == text
