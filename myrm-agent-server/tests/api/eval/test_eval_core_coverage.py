from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.eval.capture import capture_case_from_chat
from app.core.eval.datasets import get_eval_cases, save_eval_cases
from app.core.eval.reports import get_all_report_summaries, get_latest_report_summary


class MockMsg:
    def __init__(self, role, content, extra_data=None):
        self.role = role
        self.content = content
        self.extra_data = extra_data


class MockToolPydantic(BaseModel):
    name: str
    args: dict


class MockToolDataclass:
    def __init__(self):
        self.name = "dc_tool"


@pytest.mark.asyncio
async def test_capture_case_from_chat_edge_cases(tmp_path):
    chat_id = "test_chat_123"
    dataset_id = "test_ds_123"

    # 1. No messages
    with patch("app.services.chat.chat_service.ChatService.get_all_messages", return_value=[]):
        assert await capture_case_from_chat(chat_id, dataset_id) is False

    class MockToolAttr:
        name = "attr_tool"

    # 2. Rich message types
    msgs = [
        MockMsg("user", "hello", {"tool_calls": [{"name": "dict_tool"}]}),
        MockMsg("assistant", "world", {"tool_calls": [MockToolPydantic(name="py_tool", args={})]}),
        MockMsg("user", "test", {"tool_calls": [MockToolDataclass()]}),
        MockMsg("assistant", "test2", {"tool_calls": [MockToolAttr()]}),
    ]
    with patch("app.services.chat.chat_service.ChatService.get_all_messages", return_value=msgs):
        with patch("app.services.chat.chat_service.ChatService.get_chat_metadata", return_value=MagicMock(agent_id="test_agent")):
            with patch("app.core.eval.capture.save_eval_cases", return_value=True) as mock_save:
                with patch("app.core.eval.capture.get_eval_cases", return_value="{}"):
                    assert await capture_case_from_chat(chat_id, dataset_id) is True
                    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_capture_case_from_chat_dataclass_and_name_only_tools():
    """Dataclass tool calls dump via asdict; plain name-only objects via name attr."""
    from dataclasses import dataclass
    from unittest.mock import patch

    from app.core.eval.capture import capture_case_from_chat

    @dataclass
    class DCTool:
        name: str = "dc_tool"
        args: dict = None

    class NameOnlyTool:
        name = "name_tool"

    msgs = [
        MockMsg("user", "hello", {"tool_calls": [DCTool()]}),
        MockMsg("assistant", "world", {"tool_calls": [NameOnlyTool()]}),
    ]
    with patch("app.services.chat.chat_service.ChatService.get_all_messages", return_value=msgs):
        with patch("app.services.chat.chat_service.ChatService.get_chat_metadata", return_value=MagicMock(agent_id="test_agent")):
            with patch("app.core.eval.capture.save_eval_cases", return_value=True) as mock_save:
                with patch("app.core.eval.capture.get_eval_cases", return_value="{}"):
                    assert await capture_case_from_chat("chat-dc", "ds-dc") is True
                    mock_save.assert_called_once()


@pytest.mark.asyncio
async def test_capture_case_from_chat_empty_existing_cases():
    """When no existing cases, content starts fresh (no leading newline handling)."""
    from unittest.mock import patch

    from app.core.eval.capture import capture_case_from_chat

    msgs = [MockMsg("user", "hello", None), MockMsg("assistant", "world", None)]
    with patch("app.services.chat.chat_service.ChatService.get_all_messages", return_value=msgs):
        with patch("app.services.chat.chat_service.ChatService.get_chat_metadata", return_value=MagicMock(agent_id="test_agent")):
            with patch("app.core.eval.capture.save_eval_cases", return_value=True) as mock_save:
                with patch("app.core.eval.capture.get_eval_cases", return_value=""):
                    assert await capture_case_from_chat("chat-empty", "ds-empty") is True
                    mock_save.assert_called_once()


def test_eval_service_report_summaries(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    # Empty dir
    assert get_all_report_summaries(reports_dir) == []

    # Write some reports
    r1 = reports_dir / "eval_report_100.jsonl"
    r1.write_text('{"type": "summary", "pass_rate": 1.0}\n{"type": "result"}')
    r2 = reports_dir / "eval_report_200.jsonl"
    r2.write_text('{"type": "summary", "pass_rate": 0.5}\n')
    r3 = reports_dir / "eval_report_invalid.jsonl"
    r3.write_text("invalid json")

    summaries = get_all_report_summaries(reports_dir)
    assert len(summaries) == 2
    assert summaries[0]["pass_rate"] == 0.5  # 200 is newer based on timestamp sort (mtime based usually, or parsed from filename)
    assert summaries[1]["pass_rate"] == 1.0

    # test latest
    latest_link = reports_dir / "latest.jsonl"
    latest_link.write_text('{"type": "summary", "pass_rate": 0.8}\n{"type": "result"}')

    latest = get_latest_report_summary(reports_dir)
    assert latest["pass_rate"] == 0.8
    assert len(latest["cases"]) == 1


def test_eval_service_exceptions(tmp_path):
    # test read/write exceptions gracefully handled
    invalid_path = tmp_path / "non_existent"

    with patch("app.core.eval.datasets.get_dataset_path", return_value=invalid_path):
        assert get_eval_cases("test") == ""
        # writing to a directory that is not writable
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_file = readonly_dir / "cases.jsonl"
        readonly_file.touch()
        readonly_file.chmod(0o444)
        with patch("app.core.eval.datasets.get_dataset_path", return_value=readonly_file):
            save_eval_cases("test", "test")  # Should log warning, return False or handle gracefully


def test_report_summary_edge_cases(tmp_path):
    """Edge branches of report summary readers (missing dirs, empty files, non-summary)."""
    from app.core.eval.reports import get_all_report_summaries, get_latest_report_summary

    # Missing reports dir
    missing = tmp_path / "missing"
    assert get_latest_report_summary(missing) is None
    assert get_all_report_summaries(missing) == []

    # Empty latest file
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / "latest.jsonl").write_text("")
    assert get_latest_report_summary(empty_dir) is None

    # First line is not a summary
    non_summary_dir = tmp_path / "non_summary"
    non_summary_dir.mkdir()
    (non_summary_dir / "latest.jsonl").write_text('{"type": "result"}')
    assert get_latest_report_summary(non_summary_dir) is None

    # First line not a dict
    not_dict_dir = tmp_path / "not_dict"
    not_dict_dir.mkdir()
    (not_dict_dir / "latest.jsonl").write_text('["array"]')
    assert get_latest_report_summary(not_dict_dir) is None

    # Corrupt JSON in latest
    corrupt_dir = tmp_path / "corrupt"
    corrupt_dir.mkdir()
    (corrupt_dir / "latest.jsonl").write_text("{bad json")
    assert get_latest_report_summary(corrupt_dir) is None

    # Historical reports: corrupt file skipped; non-summary first line skipped
    hist_dir = tmp_path / "hist"
    hist_dir.mkdir()
    (hist_dir / "eval_report_bad.jsonl").write_text("{oops")
    (hist_dir / "eval_report_300.jsonl").write_text('{"type": "result"}')
    assert get_all_report_summaries(hist_dir) == []

    # Historical reports: non-numeric filename timestamp falls back to mtime
    import json as _json

    ts_dir = tmp_path / "ts"
    ts_dir.mkdir()
    target = ts_dir / "eval_report_abc.jsonl"
    target.write_text(_json.dumps({"type": "summary", "pass_rate": 0.9}) + "\n")
    summaries = get_all_report_summaries(ts_dir)
    assert len(summaries) == 1
    assert summaries[0]["filename"] == "eval_report_abc.jsonl"
    assert isinstance(summaries[0]["timestamp"], int)
