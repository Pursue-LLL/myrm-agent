"""Unit tests for per-turn disclosure metadata (evidence tier, staged drafts).

The harness publishes these on the MESSAGE_END event; the collector persists
them as message metadata so the WebUI/Tauri badge and the staged-deliverable
notice can render from real runs instead of seeded fixtures.
"""

from app.services.agent.streaming_support.stream_collector import StreamContentCollector


def test_message_end_persists_deliverable_tier() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "message_end",
            "messageId": "msg-1",
            "completion_status": "complete",
            "deliverable_tier": {
                "tier": "VERIFIED",
                "evidence": {"verification_count": 2, "verification_categories": ["test"], "details": "2 verifications passed"},
            },
        }
    )

    extra_data = collector.extra_data
    assert extra_data is not None
    tier = extra_data["deliverableTier"]
    assert tier["tier"] == "VERIFIED"
    assert tier["evidence"]["verification_categories"] == ["test"]


def test_message_end_persists_staged_artifacts() -> None:
    collector = StreamContentCollector()

    collector.feed_event(
        {
            "type": "message_end",
            "messageId": "msg-2",
            "staged_artifacts": [
                {
                    "filename": "draft_worker.py",
                    "relative_path": ".myrm/staged_artifacts/draft_worker.py",
                    "full_path": "/workspace/.myrm/staged_artifacts/draft_worker.py",
                }
            ],
        }
    )

    extra_data = collector.extra_data
    assert extra_data is not None
    assert extra_data["stagedArtifacts"][0]["filename"] == "draft_worker.py"


def test_message_end_without_disclosure_leaves_metadata_clean() -> None:
    collector = StreamContentCollector()

    collector.feed_event({"type": "message_end", "messageId": "msg-3", "completion_status": "complete"})

    extra_data = collector.extra_data
    assert extra_data is None or "deliverableTier" not in extra_data
    assert extra_data is None or "stagedArtifacts" not in extra_data
