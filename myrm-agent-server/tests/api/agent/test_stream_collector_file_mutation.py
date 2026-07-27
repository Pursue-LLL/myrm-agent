"""StreamContentCollector persistence for file_mutation_failed events."""

from __future__ import annotations

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def test_file_mutation_failed_persisted_in_extra_data() -> None:
    collector = StreamContentCollector(chat_id="chat_mut")
    collector.feed_event(
        {
            "type": "file_mutation_failed",
            "data": {
                "failed_count": 1,
                "files": [
                    {
                        "path": "empty_write_e2e.txt",
                        "tool": "file_write_tool",
                        "error_preview": "Cannot write empty file content",
                    }
                ],
            },
        }
    )

    extra = collector.extra_data
    assert extra is not None
    failures = extra.get("fileMutationFailures")
    assert isinstance(failures, list)
    assert len(failures) == 1
    row = failures[0]
    assert row["path"] == "empty_write_e2e.txt"
    assert row["tool"] == "file_write_tool"
    assert "Cannot write empty file content" in str(row["error_preview"])


def test_file_mutation_failed_ignores_invalid_payload() -> None:
    collector = StreamContentCollector(chat_id="chat_mut_invalid")
    collector.feed_event({"type": "file_mutation_failed", "data": {"files": "bad"}})
    collector.feed_event(
        {
            "type": "file_mutation_failed",
            "data": {
                "files": [
                    {"path": "", "tool": "file_write_tool", "error_preview": "x"}
                ],
            },
        }
    )

    extra = collector.extra_data
    assert extra is None or extra.get("fileMutationFailures") in (None, [])
