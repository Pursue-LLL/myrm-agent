from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_clarification_required,
    collect_plan_confirmation_status,
)


def test_collect_clarification_required_deep_research_source() -> None:
    payload = collect_clarification_required(
        {
            "type": "clarification_required",
            "data": {
                "type": "ask_question",
                "source": "deep_research",
                "form": {
                    "questions": [{"id": "q1", "prompt": "Which one?"}],
                },
            },
        }
    )
    assert payload is not None
    assert payload["isResumeMode"] is False
    assert payload["answered"] is False


def test_collect_plan_confirmation_waiting() -> None:
    payload = collect_plan_confirmation_status(
        {
            "phase": "plan_confirm",
            "status": "waiting",
            "plan": "Step 1",
        }
    )
    assert payload is not None
    assert payload["status"] == "waiting"
    assert payload["source"] == "deep_research"
