"""The numbers the bash tool states to the model are the numbers the code runs with.

They live in the ``BashInput`` field texts only: the static description repeats none of them
(``test_tool_description``), and the concurrent-job cap reaches the model in the quota error, which formats the
live limit (``BackgroundQuotaError``).
"""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.bash._executor.auto_yield import DEFAULT_YIELD_AFTER_SECONDS
from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import BashInput
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig


def _field_text(name: str) -> str:
    return BashInput.model_fields[name].description or ""


def _schema_maximum(name: str) -> int:
    branches = BashInput.model_json_schema()["properties"][name]["anyOf"]
    return next(branch["maximum"] for branch in branches if "maximum" in branch)


def test_the_timeout_text_states_the_default_and_the_ceiling_the_code_applies() -> None:
    text = _field_text("timeout")

    assert f"default {ExecutionConfig().local.max_execution_time}" in text
    assert f"max {_schema_maximum('timeout')}" in text


def test_the_yield_default_in_the_field_text_is_the_one_the_code_applies() -> None:
    assert f"default {DEFAULT_YIELD_AFTER_SECONDS}" in _field_text("yield_after_seconds")
