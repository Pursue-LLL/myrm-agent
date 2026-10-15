"""Architecture test: every server-built agent run reads the persisted privacy switch.

The web chat converter takes the privacy settings from the request. Any other place that builds
``GeneralAgentParams`` has no request, so it must pull them from the persisted settings through
``privacy_agent_params``; otherwise turning privacy on in the settings page silently covers only the web chat.
Runs resumed from a stored snapshot (``model_validate`` of serialized params) keep the policy of the turn they resume.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"

_EXEMPT = {
    "services/agent/params/converter.py": "web chat: the privacy settings arrive in the request",
    "core/eval/executor.py": "evaluation replays developer-authored cases; masking would distort the comparison",
}
# Builds the run params by copying an existing instance instead of calling the constructor.
_COPY_CARRIERS = ("services/agent/wakeup_handler.py",)


def _is_name(node: ast.expr, name: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == name) or (isinstance(node, ast.Attribute) and node.attr == name)


def _calls(source: str, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and _is_name(n.func, name)]


def _splats_privacy_params(call: ast.Call) -> bool:
    return any(
        kw.arg is None and isinstance(kw.value, ast.Call) and _is_name(kw.value.func, "privacy_agent_params")
        for kw in call.keywords
    )


def unguarded_constructor_lines(source: str) -> list[int]:
    """Line numbers of ``GeneralAgentParams(...)`` calls that do not splat ``privacy_agent_params(...)``."""
    return [c.lineno for c in _calls(source, "GeneralAgentParams") if not _splats_privacy_params(c)]


@cache
def _builders() -> list[str]:
    candidates = [(p, p.read_text(encoding="utf-8")) for p in _APP.rglob("*.py")]
    return sorted(
        path.relative_to(_APP).as_posix()
        for path, text in candidates
        if "GeneralAgentParams(" in text and _calls(text, "GeneralAgentParams")
    )


def test_detector_flags_a_constructor_that_forgets_the_privacy_params() -> None:
    assert unguarded_constructor_lines("p = GeneralAgentParams(query='x')") == [1]
    assert unguarded_constructor_lines("p = mod.GeneralAgentParams(query='x', **other())") == [1]


def test_detector_accepts_the_splat_and_ignores_unrelated_calls() -> None:
    assert unguarded_constructor_lines("p = GeneralAgentParams(query='x', **privacy_agent_params(s))") == []
    assert unguarded_constructor_lines("p = GeneralAgentParams(**mod.privacy_agent_params(s), query='x')") == []
    assert unguarded_constructor_lines("OtherParams(query='x')\nGeneralAgentParams.model_rebuild()") == []


def test_the_scan_sees_the_known_builders() -> None:
    assert len(_builders()) >= 8, "the source scan found fewer builders than exist; the guard is blind"


def test_every_exemption_is_still_a_builder() -> None:
    assert set(_EXEMPT) <= set(_builders()), "an exempt file no longer builds GeneralAgentParams; drop the entry"


@pytest.mark.architecture
@pytest.mark.parametrize("relative_path", [path for path in _builders() if path not in _EXEMPT])
def test_builder_reads_the_persisted_privacy_switch(relative_path: str) -> None:
    lines = unguarded_constructor_lines((_APP / relative_path).read_text(encoding="utf-8"))

    assert not lines, (
        f"{relative_path} line(s) {lines} build GeneralAgentParams without **privacy_agent_params(...): "
        "a run it starts would ignore the privacy switch"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("relative_path", _COPY_CARRIERS)
def test_copy_carrier_applies_the_persisted_privacy_switch(relative_path: str) -> None:
    source = (_APP / relative_path).read_text(encoding="utf-8")

    assert _calls(source, "privacy_agent_params"), f"{relative_path} copies run params without applying privacy_agent_params()"
