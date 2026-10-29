"""The approval card of a channel turn: worded in the sender's language, honest about the time limit.

Tool names and the reasons the harness did not code are shown as they come; the sentence around them, a coded reason,
the timeout line, the security-reviewer prefix and the buttons come from the channel catalog.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode

from app.channels.types import ApprovalExpiry
from app.core.channel_bridge.agent_executor.approval_card import build_approval_card

_LOCALES = ["en", "ja", "zh-CN", "zh-TW"]
_SESSION = "telegram:dm:u1:e=2026-10-26"
_ONE_TOOL: dict[str, object] = {
    "actionRequests": [{"action": "shell", "description": "run the build"}],
    "extensions": {"timeout": {"seconds": 120, "behavior": "deny"}},
}


def _two_tools() -> dict[str, object]:
    return {**_ONE_TOOL, "actionRequests": [{"action": "shell", "description": "run the build"}, {"action": "write_file"}]}


def test_the_english_card_names_the_tool_the_reason_and_the_time_limit() -> None:
    card = build_approval_card(_ONE_TOOL, locale="en", session_key=_SESSION)

    assert card.label == "shell needs approval: run the build\n⏱ Timeout: 120s (auto-deny)"
    assert [(q.label, q.text) for q in card.quick_replies] == [("✅ Approve", "/approve"), ("❌ Deny", "/deny")]
    assert card.expiry == ApprovalExpiry(seconds=120, behavior="deny")


@pytest.mark.parametrize("locale", _LOCALES)
def test_every_part_of_the_card_comes_from_the_catalog_in_the_senders_language(locale: str) -> None:
    card = build_approval_card({**_two_tools(), "reviewConfigs": [{"smartDenied": True}]}, locale=locale, session_key=_SESSION)
    english = build_approval_card({**_two_tools(), "reviewConfigs": [{"smartDenied": True}]}, locale="en", session_key=_SESSION)

    assert "shell, write_file" in card.label and "run the build" in card.label  # tool names and reasons are not translated
    assert "approval_" not in card.label and all("approval_" not in q.label for q in card.quick_replies)
    assert [q.text for q in card.quick_replies] == ["/approve", "/deny", "/batch a,a"]  # the commands are not words
    if locale != "en":
        first_line, timeout_line = card.label.split("\n")
        assert first_line.removeprefix("⚠️") != english.label.split("\n")[0].removeprefix("⚠️")
        assert timeout_line != english.label.split("\n")[1]
        assert [q.label for q in card.quick_replies] != [q.label for q in english.quick_replies]


@pytest.mark.parametrize("locale", _LOCALES)
def test_the_security_reviewers_recommendation_leads_the_card_in_the_senders_language(locale: str) -> None:
    plain = build_approval_card(_ONE_TOOL, locale=locale, session_key=_SESSION)
    flagged = build_approval_card(
        {**_ONE_TOOL, "reviewConfigs": [{"smartDenied": False}, {"smartDenied": True}]}, locale=locale, session_key=_SESSION
    )

    assert flagged.label.endswith(plain.label)
    prefix = flagged.label.removesuffix(plain.label).strip()
    assert prefix and "approval_" not in prefix


def test_the_card_names_the_session_of_the_run_that_asks() -> None:
    assert build_approval_card(_ONE_TOOL, locale="en", session_key=_SESSION).session_key == _SESSION


def test_a_batch_gets_the_answer_for_all_and_the_per_tool_answer() -> None:
    card = build_approval_card(_two_tools(), locale="en", session_key=_SESSION)

    assert [(q.label, q.text) for q in card.quick_replies] == [
        ("✅ Approve All", "/approve"),
        ("❌ Deny All", "/deny"),
        ("📋 Batch", "/batch a,a"),
    ]


def test_a_request_without_a_reason_does_not_end_in_a_dangling_colon() -> None:
    card = build_approval_card({"actionRequests": [{"action": "shell"}]}, locale="en", session_key=_SESSION)

    assert card.label.split("\n")[0] == "shell needs approval"


@pytest.mark.parametrize(("behavior", "wording"), [("deny", "auto-deny"), ("allow", "auto-approve")])
def test_the_card_states_what_the_timeout_decides(behavior: str, wording: str) -> None:
    data = {**_ONE_TOOL, "extensions": {"timeout": {"seconds": 90, "behavior": behavior}}}

    card = build_approval_card(data, locale="en", session_key=_SESSION)

    assert card.label.endswith(f"⏱ Timeout: 90s ({wording})")
    assert card.expiry == ApprovalExpiry(seconds=90, behavior="allow" if behavior == "allow" else "deny")


def test_a_long_time_limit_is_written_without_a_thousands_separator() -> None:
    data = {**_ONE_TOOL, "extensions": {"timeout": {"seconds": 3600.0}}}

    card = build_approval_card(data, locale="en", session_key=_SESSION)

    assert "3600s" in card.label
    assert card.expiry == ApprovalExpiry(seconds=3600.0, behavior="deny")


@pytest.mark.parametrize(
    "extensions",
    [{}, {"timeout": "soon"}, {"timeout": {"seconds": "later"}}, "not-a-dict"],
    ids=["empty", "text", "bad-seconds", "no-dict"],
)
def test_a_missing_or_unreadable_time_limit_falls_back_to_the_default_wait(extensions: object) -> None:
    card = build_approval_card({**_ONE_TOOL, "extensions": extensions}, locale="en", session_key=_SESSION)

    assert card.expiry == ApprovalExpiry(seconds=300.0, behavior="deny")
    assert "⏱ Timeout: 300s (auto-deny)" in card.label


def test_a_request_without_action_requests_uses_the_single_tool_fields() -> None:
    card = build_approval_card({"tool_name": "browser", "reason": "open the page"}, locale="en", session_key=_SESSION)

    assert card.label.startswith("browser needs approval: open the page")
    assert len(card.quick_replies) == 2


def test_a_language_without_a_catalog_reads_in_english() -> None:
    card = build_approval_card(_ONE_TOOL, locale="xx", session_key=_SESSION)

    assert card.label == build_approval_card(_ONE_TOOL, locale="en", session_key=_SESSION).label


def _coded(code: str, subject: str = "") -> dict[str, object]:
    request: dict[str, object] = {"action": "file_read_tool", "description": "Path outside allowed zones: /x", "reasonCode": code}
    if subject:
        request["reasonSubject"] = subject
    return {**_ONE_TOOL, "actionRequests": [request]}


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("code", list(ApprovalReasonCode))
def test_every_code_the_harness_can_send_is_worded_in_every_catalog_language(code: ApprovalReasonCode, locale: str) -> None:
    card = build_approval_card(_coded(code.value, "/data/spec.md"), locale=locale, session_key=_SESSION)
    english = build_approval_card(_coded(code.value, "/data/spec.md"), locale="en", session_key=_SESSION)

    first_line = card.label.split("\n")[0]
    assert "approval_reason_" not in first_line and "Path outside allowed zones" not in first_line
    if code is not ApprovalReasonCode.SHELL_THREAT:
        assert "/data/spec.md" in first_line  # the subject sits inside the sentence
    if locale != "en":
        assert first_line != english.label.split("\n")[0]


def test_a_code_the_catalog_does_not_know_shows_the_reason_as_written() -> None:
    card = build_approval_card(_coded("a_future_code", "/x"), locale="zh-CN", session_key=_SESSION)

    assert "Path outside allowed zones: /x" in card.label


def test_a_batch_words_each_coded_reason_and_keeps_the_others_as_written() -> None:
    data = {
        **_ONE_TOOL,
        "actionRequests": [
            {
                "action": "web_fetch",
                "description": "Domain 'a.org' requires approval",
                "reasonCode": "domain_requires_approval",
                "reasonSubject": "a.org",
            },
            {"action": "shell", "description": "run the build"},
        ],
    }

    first_line = build_approval_card(data, locale="en", session_key=_SESSION).label.split("\n")[0]

    assert first_line == "web_fetch, shell needs approval: This domain is not on the allowed list: a.org; run the build"
