"""Unit tests for draft_notification event publishing functions.

Covers the SSE event publish helpers (DRY refactor):
- publish_skill_growth_event emits SKILL_GROWTH_UPDATED with correct payload
- _publish_new_skill_draft_event emits NEW_SKILL_DRAFT with correct payload
- _publish_sse_event swallows and logs bus failures (no crash)
"""

from unittest.mock import MagicMock, patch

from app.services.event.app_event_bus import AppEventType
from app.services.skills.draft_notification import (
    _publish_new_skill_draft_event,
    _publish_sse_event,
    publish_skill_growth_event,
)


def test_publish_skill_growth_event_emits_updated() -> None:
    bus = MagicMock()
    with patch("app.services.skills.draft_notification.get_event_bus", return_value=bus):
        publish_skill_growth_event(
            case_id="case-1",
            draft_type="skill_draft",
            status="PENDING_REVIEW",
            name="demo-skill",
        )

    bus.publish.assert_called_once()
    event = bus.publish.call_args.args[0]
    assert event.event_type == AppEventType.SKILL_GROWTH_UPDATED
    assert event.data == {
        "case_id": "case-1",
        "draft_type": "skill_draft",
        "status": "PENDING_REVIEW",
        "name": "demo-skill",
    }


def test_publish_new_skill_draft_event_emits_new_draft() -> None:
    bus = MagicMock()
    with patch("app.services.skills.draft_notification.get_event_bus", return_value=bus):
        _publish_new_skill_draft_event(draft_id="draft-1", draft_type="skill_patch", name="patch-skill")

    bus.publish.assert_called_once()
    event = bus.publish.call_args.args[0]
    assert event.event_type == AppEventType.NEW_SKILL_DRAFT
    assert event.data == {
        "draft_id": "draft-1",
        "draft_type": "skill_patch",
        "name": "patch-skill",
    }


def test_publish_sse_event_swallows_bus_failure() -> None:
    bus = MagicMock()
    bus.publish.side_effect = RuntimeError("bus down")
    with patch("app.services.skills.draft_notification.get_event_bus", return_value=bus):
        _publish_sse_event(AppEventType.SKILL_GROWTH_UPDATED, {"case_id": "x"})
    # Must not raise; failure is logged internally.
    bus.publish.assert_called_once()
