"""The ``cron_manage`` description says nothing the tool does not do, in English and in Chinese.

Every checkable sentence of the description is a ``Claim``: the words that must be in it and a check, in
``tests/support/cron_tool_claims.py``, that runs the behavior the sentence promises against the real tool, manager and
scheduler over the in-memory store. Facts that do not depend on the language (parameter names, numbers, zone names,
literal values) must be in both texts; the wording of a sentence is pinned in each language by its own phrase. Editing
a sentence in one language therefore fails here until the claim and the other language follow, and changing a
behavior fails the claim that promises it.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest

from myrm_agent_harness.toolkits.cron import (
    CRON_MANAGE_TOOL_DESCRIPTION_EN,
    CRON_MANAGE_TOOL_DESCRIPTION_ZH,
    resolve_cron_tool_description,
)
from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from tests.support import cron_tool_claims as promise
from tests.support.cron_manager_stack import make_manager_stack
from tests.support.cron_tool_claims import ACTIONS, NEW_YORK, SHANGHAI, OkRunner, World


@dataclass(frozen=True)
class Claim:
    """One sentence of the description: what both texts carry, what each language words it with, and its behavior."""

    name: str
    check: Callable[[World], Awaitable[None]]
    both: tuple[str, ...] = ()
    en: tuple[str, ...] = ()
    zh: tuple[str, ...] = ()


CLAIMS = (
    Claim(
        "one_schedule",
        promise.one_schedule,
        both=("cron_expr / every_minutes / at",),
        en=("ONE schedule param",),
        zh=("恰好一种调度参数",),
    ),
    Claim(
        "recurring_needs_confirmation",
        promise.recurring_needs_confirmation,
        both=("recurring_confirmed=true",),
        en=("REQUIRE recurring_confirmed",),
        zh=("必须显式传入 recurring_confirmed",),
    ),
    Claim(
        "command_excludes_prompt",
        promise.command_excludes_prompt,
        en=("Mutually exclusive with prompt",),
        zh=("与 prompt 互斥",),
    ),
    Claim(
        "reminder_takes_a_prompt_only",
        promise.reminder_takes_a_prompt_only,
        en=("command not allowed",),
        zh=("禁止传 command",),
    ),
    Claim(
        "blueprint_brings_its_schedule",
        promise.blueprint_brings_its_schedule,
        both=("blueprint_values",),
        en=("schedule template",),
        zh=("调度规则",),
    ),
    Claim(
        "event_trigger_needs_no_schedule",
        promise.event_trigger_needs_no_schedule,
        both=("stream_url", "poll_url"),
        en=("default: every 5 minutes",),
        zh=("默认每 5 分钟",),
    ),
    Claim("every_minutes_floor", promise.every_minutes_floor, en=("integer, minimum 5",), zh=("最小值为 5",)),
    Claim(
        "cron_gap_floor",
        promise.cron_gap_floor,
        en=("at most once per 5 minutes",),
        zh=("每 5 分钟内最多触发一次",),
    ),
    Claim("at_is_in_the_future", promise.at_is_in_the_future, en=("in the future",), zh=("须晚于当前时间",)),
    Claim(
        "tz_reads_every_wall_clock_time",
        promise.tz_reads_every_wall_clock_time,
        both=(SHANGHAI, NEW_YORK, "UTC", "+08:00"),
        en=("do not convert it to UTC", "(cron_expr, at, the active window, ISO expires_after)"),
        zh=("不要自行换算成 UTC", "（cron_expr、at、活跃时间窗口、ISO 格式的 expires_after）"),
    ),
    Claim(
        "tz_falls_back",
        promise.tz_falls_back,
        en=("on update the task's own timezone, else the user's timezone, else UTC",),
        zh=("update 沿用任务自己的时区，否则按用户所在时区，未知则按 UTC",),
    ),
    Claim(
        "active_window",
        promise.active_window,
        both=("active_start", "active_end", "active_tz"),
        en=("give active_end too", "(defaults to tz)"),
        zh=("需同时给出 active_end", "（默认同 tz）"),
    ),
    Claim(
        "max_fires",
        promise.max_fires,
        both=("max_fires",),
        en=("0 = unlimited; on update, 0 keeps the current limit",),
        zh=("0 表示无限制；update 时 0 表示保持当前限制",),
    ),
    Claim(
        "expires_after",
        promise.expires_after,
        both=("3d", "2w", "3m", "ISO 8601"),
        en=('"3d" days, "2w" weeks, "3m" months',),
        zh=('"3d" 天、"2w" 周、"3m" 月',),
    ),
    Claim(
        "run_is_a_trial",
        promise.run_is_a_trial,
        en=("Run a task once now as a test. Its schedule, run count and one-time status stay unchanged",),
        zh=("立即试跑一次任务；不改变其调度、运行次数与一次性任务的状态",),
    ),
    Claim("session_modes", promise.session_modes, both=('"isolated"', '"main"', '"daily"')),
    Claim(
        "names",
        promise.names,
        en=("auto-generated if omitted", "Fuzzy filter keyword"),
        zh=("省略时将根据 prompt/command 自动生成", "模糊过滤关键词"),
    ),
    Claim("model", promise.model, en=("current chat model",), zh=("当前对话所用的模型",)),
    Claim("tools_allowed", promise.tools_allowed, both=('"web_search,memory"',)),
    Claim(
        "poll_interval",
        promise.poll_interval,
        both=("poll_interval_seconds",),
        en=("minimum 60, default 300",),
        zh=("最小 60 秒，默认 300 秒",),
    ),
    Claim("monitor", promise.monitor, both=('"set"', '"hash"', '"off"')),
    Claim("context_from", promise.context_from, both=("context_from",)),
)


@pytest.mark.parametrize("locale", ["en", "zh"])
@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: claim.name)
def test_the_description_carries_the_sentence_of_every_claim(claim: Claim, locale: str) -> None:
    text = resolve_cron_tool_description(locale)
    wording = claim.en if locale == "en" else claim.zh

    assert [phrase for phrase in (*claim.both, *wording) if phrase not in text] == []


@pytest.mark.parametrize("claim", CLAIMS, ids=lambda claim: claim.name)
async def test_the_tool_does_what_the_sentence_promises(claim: Claim) -> None:
    await claim.check(World(make_manager_stack(OkRunner())))


def _bullet_names(text: str) -> set[str]:
    """The identifiers the description lists as ``- name: ...`` (Chinese uses a full-width colon)."""
    return set(re.findall(r"^- (\w+)\s*[:：]", text, flags=re.MULTILINE))


def test_both_languages_list_the_same_actions_and_parameters() -> None:
    assert _bullet_names(CRON_MANAGE_TOOL_DESCRIPTION_EN) == _bullet_names(CRON_MANAGE_TOOL_DESCRIPTION_ZH)


@pytest.mark.parametrize("text", [CRON_MANAGE_TOOL_DESCRIPTION_EN, CRON_MANAGE_TOOL_DESCRIPTION_ZH], ids=["en", "zh"])
def test_the_description_lists_every_action_and_every_parameter_of_the_tool_and_nothing_else(text: str) -> None:
    tool = create_cron_tools(make_manager_stack().manager)[0]

    assert _bullet_names(text) - ACTIONS == set(tool.args)
    assert _bullet_names(text) >= ACTIONS


@pytest.mark.parametrize("text", [CRON_MANAGE_TOOL_DESCRIPTION_EN, CRON_MANAGE_TOOL_DESCRIPTION_ZH], ids=["en", "zh"])
def test_the_description_names_no_provider_internals(text: str) -> None:
    assert "LiteLLM" not in text


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        (None, CRON_MANAGE_TOOL_DESCRIPTION_EN),
        ("en-US", CRON_MANAGE_TOOL_DESCRIPTION_EN),
        ("zh-CN", CRON_MANAGE_TOOL_DESCRIPTION_ZH),
    ],
)
def test_the_tool_carries_the_description_of_its_locale(locale: str | None, expected: str) -> None:
    tool = create_cron_tools(make_manager_stack().manager, description_locale=locale)[0]

    assert tool.description == expected
