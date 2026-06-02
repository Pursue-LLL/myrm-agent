from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.eval.capture import capture_case_from_chat
from app.core.eval.service import get_all_report_summaries, get_eval_cases, get_latest_report_summary, save_eval_cases


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
        MockMsg("assistant", "test2", {"tool_calls": [MockToolAttr()]})
    ]
    with patch("app.services.chat.chat_service.ChatService.get_all_messages", return_value=msgs):
        with patch("app.services.chat.chat_service.ChatService.get_chat_metadata", return_value=MagicMock(agent_id="test_agent")):
            with patch("app.core.eval.capture.save_eval_cases", return_value=True) as mock_save:
                with patch("app.core.eval.capture.get_eval_cases", return_value="{}"):
                    assert await capture_case_from_chat(chat_id, dataset_id) is True
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
    r3.write_text('invalid json')

    summaries = get_all_report_summaries(reports_dir)
    assert len(summaries) == 2
    assert summaries[0]["pass_rate"] == 0.5 # 200 is newer based on timestamp sort (mtime based usually, or parsed from filename)
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
    
    with patch("app.core.eval.service.get_dataset_path", return_value=invalid_path):
        assert get_eval_cases("test") == ""
        # writing to a directory that is not writable
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_file = readonly_dir / "cases.jsonl"
        readonly_file.touch()
        readonly_file.chmod(0o444)
        with patch("app.core.eval.service.get_dataset_path", return_value=readonly_file):
            save_eval_cases("test", "test") # Should log warning, return False or handle gracefully

