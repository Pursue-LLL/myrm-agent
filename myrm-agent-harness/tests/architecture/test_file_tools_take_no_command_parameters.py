"""Architecture gate: the file tools take no command, script or program as an argument.

The permission engine rates a call by its tool's category (``file_write`` for these tools, ``code_interpreter`` for
bash) and never reads the arguments, so a command-shaped parameter on a file tool would run shell text under the file
tool's verdict, past the approval, the code-execution policy and the pre-checks the bash tool applies. What a file tool
needs run goes through the bash tool; the parameters of the three file tools stay data (paths, text, ranges).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.meta_tools.file_ops.file_edit_tool import create_file_edit_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool

_FILE_TOOLS: dict[str, Callable[[], BaseTool]] = {
    "file_read_tool": create_file_read_tool,
    "file_write_tool": create_file_write_tool,
    "file_edit_tool": create_file_edit_tool,
}

# The last word of a name says what the value is, the rule the event log applies to mask a command line.
_COMMAND_SHAPED = re.compile(r"(?:^|_)(?:command|cmd|script)$")


def _property_names(schema: object) -> Iterator[str]:
    """Every property name anywhere in a JSON schema: nested objects and ``$defs`` included."""
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            yield from properties
        for value in schema.values():
            yield from _property_names(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from _property_names(item)


@pytest.mark.parametrize("tool_name", sorted(_FILE_TOOLS))
def test_no_file_tool_parameter_is_command_shaped(tool_name: str) -> None:
    schema = _FILE_TOOLS[tool_name]().get_input_schema().model_json_schema()

    offenders = sorted({name for name in _property_names(schema) if _COMMAND_SHAPED.search(name)})

    assert offenders == [], f"{tool_name} takes a command-shaped parameter: {offenders}"


def test_the_detector_flags_command_shaped_names_at_any_depth() -> None:
    nested = {
        "properties": {"path": {"type": "string"}, "edits": {"items": {"$ref": "#/$defs/Edit"}}},
        "$defs": {"Edit": {"properties": {"old_str": {}, "post_script": {}}}},
    }

    flagged = [name for name in _property_names(nested) if _COMMAND_SHAPED.search(name)]

    assert flagged == ["post_script"]


@pytest.mark.parametrize("name", ["command", "check_command", "rerun_cmd", "cmd", "run_script", "script"])
def test_the_name_rule_matches_what_it_is_meant_to(name: str) -> None:
    assert _COMMAND_SHAPED.search(name)


@pytest.mark.parametrize("name", ["path", "paths", "reason", "old_str", "description", "scripture", "commandline_note"])
def test_the_name_rule_leaves_data_names_alone(name: str) -> None:
    assert not _COMMAND_SHAPED.search(name)
