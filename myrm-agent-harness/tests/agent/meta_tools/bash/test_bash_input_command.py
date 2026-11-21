"""BashInput command validation tests.

A command with no content runs nothing, so the schema refuses it with the cause: the model reads what to fix instead
of meeting a security block for text it never wrote.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool

_REASON = "List workspace files for review"


@pytest.fixture(scope="module")
def tool_schema() -> type[BaseModel]:
    """The schema the registered tool validates against, so no test passes on a model the tool does not use."""
    schema = create_bash_code_execute_tool().args_schema
    assert isinstance(schema, type)
    assert issubclass(schema, BaseModel)
    return schema


def test_an_empty_command_is_rejected(tool_schema: type[BaseModel]) -> None:
    with pytest.raises(ValidationError, match="command must not be empty"):
        tool_schema(reason=_REASON, command="")


@pytest.mark.parametrize("command", [" ", "\n", " \t\r\n "])
def test_a_blank_command_is_rejected(tool_schema: type[BaseModel], command: str) -> None:
    with pytest.raises(ValidationError, match="command must not be empty"):
        tool_schema(reason=_REASON, command=command)


def test_a_command_with_content_is_accepted_as_typed(tool_schema: type[BaseModel]) -> None:
    model = tool_schema(reason=_REASON, command="  ls -la\n")

    assert model.model_dump()["command"] == "  ls -la\n"
