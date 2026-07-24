"""Unit tests for desktop dref extraction from API messages."""

from __future__ import annotations

from tests.e2e.desktop_approval.trust_api import extract_first_desktop_dref_from_messages


def test_extract_dref_from_snapshot_stdout() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "metadata": {
                "progressSteps": [
                    {
                        "tool_name": "desktop_snapshot_tool",
                        "stdout": "TextEdit window\n  @d3 button Save",
                    }
                ]
            },
        }
    ]
    assert extract_first_desktop_dref_from_messages(messages) == "d3"


def test_extract_dref_prefers_latest_assistant() -> None:
    messages = [
        {
            "role": "assistant",
            "metadata": {"progressSteps": [{"stdout": "@d1 old"}]},
        },
        {
            "role": "assistant",
            "metadata": {"progressSteps": [{"stdout": "foreground @d7 click"}]},
        },
    ]
    assert extract_first_desktop_dref_from_messages(messages) == "d7"


def test_extract_dref_from_top_level_progress_steps() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "",
            "progressSteps": [
                {
                    "tool_name": "desktop_snapshot_tool",
                    "stdout": "TextEdit\n  @d5 button OK",
                }
            ],
        }
    ]
    assert extract_first_desktop_dref_from_messages(messages) == "d5"


def test_extract_dref_returns_none_when_missing() -> None:
    assert extract_first_desktop_dref_from_messages([]) is None
    assert (
        extract_first_desktop_dref_from_messages(
            [{"role": "assistant", "metadata": {"progressSteps": [{"stdout": "no refs"}]}}]
        )
        is None
    )
