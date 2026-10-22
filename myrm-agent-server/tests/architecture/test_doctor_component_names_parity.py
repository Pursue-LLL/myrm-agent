"""System doctor component names: backend probes and the frontend title table must agree.

[POS]
tests/architecture/test_doctor_component_names_parity.py

[INPUT]
- myrm_agent_harness and app/**: `HealthReport(component_name="<literal>")` call sites
- myrm-agent-frontend doctorReportView.ts: `COMPONENT_NAMES`

[OUTPUT]
- Fails when a probe reports a literal component name the doctor page has no localized title for
- Fails when the frontend lists a component name that no probe reports (dead locale strings)
  Hooks that time out are reported under their Python function name and are not literals, so they are outside this table.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import myrm_agent_harness
import pytest

from tests.support.frontend_api_paths import FRONTEND_SRC

_DOCTOR_VIEW = FRONTEND_SRC / "components" / "features" / "health" / "doctorReportView.ts"
_SERVER_APP = Path(__file__).resolve().parents[2] / "app"
_HARNESS_SRC = Path(myrm_agent_harness.__file__).resolve().parent

_COMPONENT_NAMES_RE = re.compile(r"COMPONENT_NAMES\s*=\s*\[(?P<body>.*?)\]\s*as const", re.DOTALL)
_QUOTED_RE = re.compile(r"'([A-Za-z0-9]+)'")


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _backend_component_names() -> set[str]:
    names: set[str] = set()
    for root in (_HARNESS_SRC, _SERVER_APP):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or _called_name(node) != "HealthReport":
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "component_name" and isinstance(keyword.value, ast.Constant):
                        if isinstance(keyword.value.value, str):
                            names.add(keyword.value.value)
    return names


def _frontend_component_names() -> set[str]:
    match = _COMPONENT_NAMES_RE.search(_DOCTOR_VIEW.read_text(encoding="utf-8"))
    assert match, f"COMPONENT_NAMES list not found in {_DOCTOR_VIEW}"
    return set(_QUOTED_RE.findall(match.group("body")))


@pytest.mark.skipif(not _DOCTOR_VIEW.is_file(), reason="frontend sources are not part of this checkout")
def test_doctor_component_names_match_between_backend_and_frontend() -> None:
    backend = _backend_component_names()
    frontend = _frontend_component_names()

    assert len(backend) > 10, "backend scan found almost no HealthReport component names; the scan is broken"
    assert not backend - frontend, (
        f"Probes report component names without a localized title in doctorReportView.ts COMPONENT_NAMES: "
        f"{sorted(backend - frontend)}"
    )
    assert not frontend - backend, (
        f"doctorReportView.ts COMPONENT_NAMES lists components no probe reports (remove them and their locale strings): "
        f"{sorted(frontend - backend)}"
    )
