"""CodeTypeDetector tests — code type detection for Bash/Python."""

import subprocess
import sys

import pytest

from myrm_agent_harness.toolkits.code_execution.code_detector import (
    CodeType,
    CodeTypeDetector,
    code_detector,
    detect_for_execution,
    runs_as_python,
)

PYTHON_SOURCE = "\n".join(
    (
        "import re",
        "tags = ['v1.2.3', 'v2']",
        "for tag in tags:",
        "    print(re.match(r'^v(\\d+)$', tag))",
        "print('done')",
    )
)


class TestRunsAsPython:
    """The predicate checks use to stand down shell-only rules exactly when no shell reads the text."""

    def test_python_source_runs_in_the_wrapper(self) -> None:
        assert runs_as_python(PYTHON_SOURCE)

    def test_a_background_spawn_is_always_a_shell(self) -> None:
        assert not runs_as_python(PYTHON_SOURCE, run_in_background=True)

    def test_a_shell_command_is_not_python(self) -> None:
        assert not runs_as_python("ls -la && echo done")

    def test_surrounding_whitespace_does_not_change_the_route(self) -> None:
        assert runs_as_python(f"\n\n  {PYTHON_SOURCE}\n")

    def test_one_markdown_fence_around_the_source_does_not_change_the_route(self) -> None:
        assert runs_as_python(f"```python\n{PYTHON_SOURCE}\n```")

    def test_it_agrees_with_the_detector_the_executor_uses(self) -> None:
        for command in (PYTHON_SOURCE, "echo hi", "python3 -c 'print(1)'", "x = await f()", ""):
            assert runs_as_python(command) == code_detector.is_python(command.strip())


class TestDetectForExecution:
    """The route every check that depends on a command's language asks for: the one the executor gives it."""

    def test_python_in_a_markdown_fence_is_python_with_the_fence_removed(self) -> None:
        result = detect_for_execution(f"```python\n{PYTHON_SOURCE}\n```")

        assert result.code_type == CodeType.PYTHON
        assert result.extracted_code == PYTHON_SOURCE

    def test_it_is_the_detector_on_the_stripped_and_unwrapped_text(self) -> None:
        for command in (PYTHON_SOURCE, "echo hi", "python3 -c 'print(1)'", f"\n  {PYTHON_SOURCE}\n"):
            assert detect_for_execution(command) == code_detector.detect(command.strip())


class TestCodeTypeDetector:
    def test_await_keyword_detected_as_async_python(self) -> None:
        result = code_detector.detect("result = await some_func()")
        assert result.code_type == CodeType.PYTHON
        assert result.is_async is True
        assert result.detection_reason.startswith("python")

    def test_python_c_command(self) -> None:
        result = code_detector.detect('python -c "print(1)"')
        assert result.code_type == CodeType.PYTHON
        assert result.extracted_code == "print(1)"
        assert "python -c" in result.detection_reason

    def test_python3_c_command_single_quotes(self) -> None:
        result = code_detector.detect("python3 -c 'import sys; print(sys.version)'")
        assert result.code_type == CodeType.PYTHON
        assert "import sys" in result.extracted_code

    def test_python_c_no_quotes_raw_fallback_to_python(self) -> None:
        """python -c with extraction failure stays PYTHON via raw fallback.

        Falling back to BASH would mean running raw Python source as a shell
        command — guaranteed to produce a cascade of cryptic ``not found``
        errors. Raw fallback keeps the language as PYTHON so downstream
        ``ast.parse`` can emit the canonical ``python -c`` hint to the LLM.
        """
        result = code_detector.detect("python -c something_without_quotes")
        assert result.code_type == CodeType.PYTHON
        assert result.extracted_code == "something_without_quotes"
        assert "raw fallback" in result.detection_reason

    def test_python_c_raw_fallback_preserves_await_async(self) -> None:
        """Raw fallback path must still detect await for async-mode dispatch."""
        cmd = "python3 -c await crazy_unquoted_token"
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.PYTHON
        assert result.is_async is True
        assert "raw fallback" in result.detection_reason

    def test_multiline_python_syntax(self) -> None:
        code = """
import os
import sys
def main():
    pass
main()
"""
        result = code_detector.detect(code)
        assert result.code_type == CodeType.PYTHON
        assert result.detection_reason.startswith("python statement")

    def test_simple_bash_command(self) -> None:
        result = code_detector.detect("ls -la")
        assert result.code_type == CodeType.BASH
        assert result.detection_reason == "default to bash"

    def test_git_command(self) -> None:
        result = code_detector.detect("git status")
        assert result.code_type == CodeType.BASH

    def test_short_code_defaults_to_bash(self) -> None:
        result = code_detector.detect("echo hello")
        assert result.code_type == CodeType.BASH

    def test_multiline_bash_stays_bash(self) -> None:
        code = "echo hello\necho world\nls"
        result = code_detector.detect(code)
        assert result.code_type == CodeType.BASH

    def test_is_python_convenience(self) -> None:
        assert code_detector.is_python("result = await func()") is True
        assert code_detector.is_python("ls -la") is False

    def test_is_bash_convenience(self) -> None:
        assert code_detector.is_bash("ls -la") is True
        assert code_detector.is_bash("result = await func()") is False

    def test_python_with_for_loop(self) -> None:
        code = """
import os
data = []
for item in range(10):
    data.append(item)
print(data)
"""
        result = code_detector.detect(code)
        assert result.code_type == CodeType.PYTHON

    def test_python_with_class_definition(self) -> None:
        code = """
import dataclasses
class Foo:
    x: int = 0
    def bar(self):
        pass
"""
        result = code_detector.detect(code)
        assert result.code_type == CodeType.PYTHON

    def test_python_with_dict_assignment(self) -> None:
        code = """
import json
x = 1
y = 2
data = {"key": "value"}
print(data)
"""
        result = code_detector.detect(code)
        assert result.code_type == CodeType.PYTHON

    def test_python_with_asyncio_run(self) -> None:
        code = """
import asyncio
async def main():
    pass
asyncio.run(main())
print("done")
"""
        result = code_detector.detect(code)
        assert result.code_type == CodeType.PYTHON

    def test_global_singleton_exists(self) -> None:
        assert isinstance(code_detector, CodeTypeDetector)

    def test_a_one_line_python_call_is_python(self) -> None:
        result = code_detector.detect("print('hello')")
        assert result.code_type == CodeType.PYTHON
        assert result.detection_reason == "python call statement"

    def test_python_c_with_nested_quotes_extracted(self) -> None:
        """python -c with nested quotes: greedy regex extracts outer content."""
        cmd = """python3 -c 'import asyncio; exec("async def main(): pass")'"""
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.PYTHON
        assert "python3" not in result.extracted_code
        assert "import asyncio" in result.extracted_code
        assert "extracted" in result.detection_reason

    def test_python_c_complex_nested_quotes_greedy_match(self) -> None:
        """Greedy regex matches from first to last quote, extracting valid Python."""
        cmd = "python3 -c 'print('hello')'"
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.PYTHON

    def test_leading_comments_do_not_make_a_shell_command_python(self) -> None:
        code = "# comment 1\n# comment 2\n# comment 3\n# comment 4\necho hello"
        result = code_detector.detect(code)
        assert result.code_type == CodeType.BASH

    def test_several_shell_lines_without_python_syntax_stay_bash(self) -> None:
        code = "echo hello\necho world\necho foo\necho bar"
        result = code_detector.detect(code)
        assert result.code_type == CodeType.BASH
        assert result.detection_reason == "default to bash"

    def test_empty_string_defaults_to_bash(self) -> None:
        result = code_detector.detect("")
        assert result.code_type == CodeType.BASH
        assert result.detection_reason == "default to bash"

    def test_python_c_with_await_extracts_then_detects_async(self) -> None:
        """python -c extraction takes priority; await is detected in extracted code."""
        cmd = 'python -c "result = await some_func()"'
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.PYTHON
        assert result.is_async is True
        assert "python -c" in result.detection_reason
        assert result.extracted_code == "result = await some_func()"

    def test_cat_heredoc_extracted_as_python(self) -> None:
        cmd = (
            "cat > /tmp/query.py << 'EOF'\n"
            "import asyncio\n"
            "from skills.mcp_12306_skill import get_tickets\n"
            "print('[RESULT] ok')\n"
            "EOF\n"
            "python3 /tmp/query.py"
        )
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.PYTHON
        assert "get_tickets" in result.extracted_code
        assert "embedded python" in result.detection_reason
        assert "cat >" not in result.extracted_code

    def test_cat_heredoc_yaml_not_misclassified_as_python(self) -> None:
        cmd = (
            "mkdir -p .myrm\n"
            "cat > .myrm/filters.yaml << 'EOF'\n"
            "filters:\n"
            "  - name: e2e-filter-run\n"
            "    match_command: 'run\\\\.sh'\n"
            "    replace:\n"
            "      - pattern: 'E2E_MASK_TOKEN=\\\\w+'\n"
            "        replacement: 'E2E_MASKED_VAL'\n"
            "    strip_lines_matching:\n"
            "      - '^E2E_DEBUG:'\n"
            "EOF"
        )
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.BASH, result.detection_reason

    def test_cat_heredoc_shell_script_not_misclassified_as_python(self) -> None:
        cmd = (
            "cat > run.sh << 'EOF'\n"
            "#!/bin/bash\n"
            "echo 'E2E_BEGIN_LINE ok'\n"
            "echo 'E2E_DEBUG: loading config'\n"
            "echo 'E2E_FINISH_LINE ok'\n"
            "EOF"
        )
        result = code_detector.detect(cmd)
        assert result.code_type == CodeType.BASH, result.detection_reason


class TestRoutingBySyntaxTree:
    """Text the executor has no wrapper for is routed by what it parses to, not by words or line counts."""

    @pytest.mark.parametrize(
        "command",
        [
            'grep -rn "await" src/',
            'grep -n "async for" app.py',
            'grep -rn "import os" .',
            "echo 'def main(): pass'",
        ],
    )
    def test_python_keywords_inside_a_shell_string_do_not_make_it_python(self, command: str) -> None:
        assert code_detector.detect(command).code_type == CodeType.BASH

    def test_unparsable_text_that_opens_like_python_goes_to_the_interpreter(self) -> None:
        """Its SyntaxError names the model's own line; a shell would only answer 'command not found'."""
        result = code_detector.detect("import os\nprint(os.listdir('.')")
        assert result.code_type == CodeType.PYTHON
        assert result.detection_reason == "python opening statement"

    def test_unparsable_text_that_does_not_open_like_python_goes_to_the_shell(self) -> None:
        assert code_detector.detect("x = 41\nprint('set', x_state").code_type == CodeType.BASH

    def test_the_opening_line_skips_leading_comments_and_blank_lines(self) -> None:
        assert code_detector.detect("# parse the log\n\nimport os\nprint(").code_type == CodeType.PYTHON

    def test_an_oversized_text_is_judged_by_its_opening_line_alone(self) -> None:
        python_opening = "import os\n" + "x = 1\n" * 10_000
        no_python_opening = "x = [1]\n" * 10_000
        assert code_detector.detect(python_opening).code_type == CodeType.PYTHON
        assert code_detector.detect(no_python_opening).code_type == CodeType.BASH
        assert code_detector.detect("echo " + "a" * 40_000).code_type == CodeType.BASH

    def test_a_top_level_await_is_reported_as_async_for_the_executor(self) -> None:
        assert code_detector.detect("result = await f()\nprint(result)").is_async is True
        assert code_detector.detect("import os\nprint(os.getcwd())").is_async is False


# Parses a command whose string holds an invalid Python escape (``"\\d+"``): the compiler warns for every parse of it.
_PARSE_WITH_THE_ROUTER = r"""
from myrm_agent_harness.toolkits.code_execution.code_detector import code_detector

code_detector.detect('result = "\\d+"')
"""
_PARSE_WITHOUT_THE_ROUTER = r"""
import ast

ast.parse('result = "\\d+"')
"""


def _stderr_of(script: str) -> str:
    done = subprocess.run([sys.executable, "-W", "default", "-c", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return done.stderr


class TestRouterWarnings:
    def test_routing_a_shell_regex_emits_no_syntax_warning(self) -> None:
        assert "SyntaxWarning" in _stderr_of(_PARSE_WITHOUT_THE_ROUTER), "the control must show the compiler warning"
        assert _stderr_of(_PARSE_WITH_THE_ROUTER) == ""
