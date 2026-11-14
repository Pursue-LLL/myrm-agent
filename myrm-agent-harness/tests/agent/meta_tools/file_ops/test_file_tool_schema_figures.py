"""The figures the file tools quote to the model are the limits the code enforces.

A description that states a number the code no longer uses misleads the model on every turn, so the quoted numbers
are tied to the constants that enforce them.
"""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.file_ops.core.batch_str_replace import MAX_EDITS_PER_CALL
from myrm_agent_harness.agent.meta_tools.file_ops.file_edit_tool import FileEditInput
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import FileReadInput
from myrm_agent_harness.agent.meta_tools.file_ops.streaming import _PREVIEW_LINES


def _description(schema: dict[str, object], name: str) -> str:
    properties = schema["properties"]
    assert isinstance(properties, dict)
    description = properties[name]["description"]
    assert isinstance(description, str)
    return description


def test_edit_schema_quotes_the_edit_limit_the_engine_enforces() -> None:
    assert f"max {MAX_EDITS_PER_CALL}," in _description(FileEditInput.model_json_schema(), "edits")


def test_read_schema_quotes_the_preview_length_the_reader_uses() -> None:
    assert f"first {_PREVIEW_LINES} lines" in _description(FileReadInput.model_json_schema(), "mode")
