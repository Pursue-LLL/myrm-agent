"""Every server-built agent run reads the persisted privacy switch.

The web chat converter takes the privacy settings from the request. Any other place that builds
``GeneralAgentParams`` has no request, so it must pull them from the persisted settings through
``privacy_agent_params``; otherwise turning privacy on in the settings page silently covers only the web chat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[3] / "app"

# Builders that are exempt, with the reason.
_EXEMPT = {
    "services/agent/params/converter.py": "web chat: the privacy settings arrive in the request",
    "core/eval/executor.py": "evaluation replays developer-authored cases; masking would distort the comparison",
}


def _all_builders() -> list[str]:
    return sorted(
        path.relative_to(_APP).as_posix()
        for path in _APP.rglob("*.py")
        if "GeneralAgentParams(" in path.read_text(encoding="utf-8") and path.name != "agent_params.py"
    )


def test_the_guard_sees_the_known_builders() -> None:
    assert len(_all_builders()) >= 8, "the source scan found fewer builders than exist; the guard is blind"


def test_every_exemption_is_still_a_builder() -> None:
    assert set(_EXEMPT) <= set(_all_builders()), "an exempt file no longer builds GeneralAgentParams; drop the entry"


@pytest.mark.parametrize("relative_path", [path for path in _all_builders() if path not in _EXEMPT])
def test_builder_reads_the_persisted_privacy_switch(relative_path: str) -> None:
    source = (_APP / relative_path).read_text(encoding="utf-8")

    assert "**privacy_agent_params(" in source, (
        f"{relative_path} builds GeneralAgentParams without privacy_agent_params(): "
        "a run it starts would ignore the privacy switch"
    )
