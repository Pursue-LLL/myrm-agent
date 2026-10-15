"""Skill evolution SSE events: payload contract and publish-failure isolation."""

from unittest.mock import patch

from app.services.skills import evolution_events

_GET_BUS = "app.services.skills.evolution_events.get_event_bus"


def test_skill_evolved_event_keeps_its_payload_contract() -> None:
    with patch(_GET_BUS) as get_bus:
        evolution_events.publish_skill_evolved_event(
            skill_name="deploy-checklist",
            evolution_type="new",
            description="d" * 300,
            evolution_id="evo-1",
        )

    event = get_bus.return_value.publish.call_args.args[0]
    assert event.event_type.value == "skill_evolved"
    assert event.data == {
        "skill_name": "deploy-checklist",
        "evolution_type": "new",
        "description": "d" * 200,
        "evolution_id": "evo-1",
        "notify": True,
    }


def test_skill_evolved_event_can_ask_the_ui_to_stay_silent() -> None:
    with patch(_GET_BUS) as get_bus:
        evolution_events.publish_skill_evolved_event(
            skill_name="deploy-checklist",
            evolution_type="new",
            description="d",
            notify=False,
        )

    assert get_bus.return_value.publish.call_args.args[0].data["notify"] is False


def test_publishing_failures_never_reach_the_caller() -> None:
    with patch(_GET_BUS, side_effect=RuntimeError("bus down")):
        evolution_events.publish_skill_evolved_event(skill_name="s", evolution_type="new", description="")
