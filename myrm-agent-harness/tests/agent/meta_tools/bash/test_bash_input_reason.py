"""BashInput reason validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import BashInput


def test_reason_requires_minimum_length() -> None:
    with pytest.raises(ValidationError):
        BashInput(reason="short", command="echo hi")


def test_reason_accepts_valid_intent() -> None:
    model = BashInput(reason="List workspace files for review", command="ls -la")
    assert model.reason == "List workspace files for review"


@pytest.mark.parametrize(
    "reason",
    [
        "1234567890",
        "查询日期与车站编码",
        "列出命名空间",
        "查询日期与",
        "查skills包",
        "파일 목록 확인",
        "ファイル確認",
    ],
)
def test_reason_floor_counts_wide_characters_as_two_columns(reason: str) -> None:
    assert BashInput(reason=reason, command="echo hi").reason == reason


@pytest.mark.parametrize("reason", ["", "   ", "run", "ls -la", "123456789", "检查", "运行脚本", "查询日期"])
def test_reason_floor_rejects_a_short_intent_in_any_script(reason: str) -> None:
    with pytest.raises(ValidationError, match="at least 10 characters wide"):
        BashInput(reason=reason, command="echo hi")


def test_reason_is_stripped_before_it_is_measured() -> None:
    assert BashInput(reason="  查询日期与车站编码  ", command="echo hi").reason == "查询日期与车站编码"
    with pytest.raises(ValidationError):
        BashInput(reason="      检查      ", command="echo hi")
