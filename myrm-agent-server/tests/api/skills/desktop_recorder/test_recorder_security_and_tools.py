"""Security and tool-contract guarantees of the Desktop Workflow Skill Recorder API.

These cover two failure modes that only show up in the compiled artifact rather than in the
recorder's own state: a secret reaching the published SKILL.md, and a declared tool that does
not exist in the registry.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from myrm_agent_harness.agent.tool_management.tool_layers import _TOOL_LAYERS

_BASE = "/api/v1/skills/desktop-recorder"


def _start(client: TestClient, session_id: str) -> None:
    res = client.post(f"{_BASE}/start", json={"session_id": session_id, "app_scope": "all"})
    assert res.status_code == 200


def _event(client: TestClient, session_id: str, **payload: object) -> None:
    res = client.post(f"{_BASE}/event", json={"session_id": session_id, **payload})
    assert res.status_code == 200, res.text


def test_secure_role_is_never_persisted_in_the_clear(client: TestClient) -> None:
    """A password field must be masked both in session state and in the compiled SKILL.md."""
    session_id = f"sec_{int(time.time())}"
    _start(client, session_id)
    _event(
        client,
        session_id,
        seq=1,
        action="type",
        app_name="SignIn",
        element_role="AXSecureTextField",
        element_title="Password",
        value="s3cr3t",
    )

    state = client.get(f"{_BASE}/session/{session_id}").json()
    events = [e for e in state["events"] if e.get("is_password")]
    assert len(events) == 1
    assert events[0]["value"] == "***"
    assert "s3cr3t" not in str(events[0])

    compiled = client.post(
        f"{_BASE}/compile-plan",
        json={"plan": client.post(f"{_BASE}/analyze-plan", json={"session_id": session_id}).json()["plan"]},
    ).json()
    assert "s3cr3t" not in compiled["markdown_content"]


def test_compiled_plan_declares_only_registered_tools(client: TestClient) -> None:
    """A compiled skill's allowed-tools must all exist, or attenuation strips real tools.

    ``_apply_allowed_tools_filter`` keeps only tools present in the declared union, so a stale
    name (``read_file`` instead of ``file_read_tool``) silently removes that capability.
    """
    session_id = f"tools_{int(time.time())}"
    _start(client, session_id)
    _event(client, session_id, seq=1, action="click", app_name="Finder", element_title="Save")

    plan = client.post(f"{_BASE}/analyze-plan", json={"session_id": session_id}).json()["plan"]
    declared = plan["allowed_tools"]
    assert declared, "a plan must declare the tools its steps rely on"
    unknown = [name for name in declared if name not in _TOOL_LAYERS]
    assert unknown == [], f"plan declares unregistered tools: {unknown}"

    compiled = client.post(f"{_BASE}/compile-plan", json={"plan": plan}).json()
    assert compiled["validation_errors"] == []
    line = next(l for l in compiled["markdown_content"].splitlines() if l.startswith("allowed-tools:"))
    for name in line.removeprefix("allowed-tools:").split():
        assert name in _TOOL_LAYERS, f"compiled SKILL.md declares unregistered tool: {name}"


def test_window_focus_produces_a_switch_step(client: TestClient) -> None:
    """A recorded window focus maps to an app-switch step, not a generic action step.

    The recorder previously compared against ``app_switch``, a literal that does not exist in
    ``RecordedActionType`` (which defines ``window_focus``), so a same-app window change fell
    through to the generic ``Execute window_focus in ...`` branch.
    """
    session_id = f"focus_{int(time.time())}"
    _start(client, session_id)
    _event(
        client,
        session_id,
        seq=1,
        action="window_focus",
        app_name="Finder",
        window_title="Main Window",
    )
    _event(
        client,
        session_id,
        seq=2,
        action="window_focus",
        app_name="Finder",
        window_title="Second Window",
    )

    steps = client.post(f"{_BASE}/analyze-plan", json={"session_id": session_id}).json()["plan"]["steps"]
    assert len(steps) == 2, f"expected both focus events to become steps, got: {[s['title'] for s in steps]}"
    for step in steps:
        assert step["title"].startswith("Switch to application"), step["title"]
        assert not step["title"].startswith("Execute"), step["title"]
        assert step["tool_hint"] == ""


def test_non_browser_app_steps_target_the_desktop_tool(client: TestClient) -> None:
    """A native-app step must suggest a desktop tool, never the shell tool for GUI clicks."""
    session_id = f"hint_{int(time.time())}"
    _start(client, session_id)
    _event(
        client,
        session_id,
        seq=1,
        action="window_focus",
        app_name="Finder",
        window_title="Main Window",
    )
    _event(client, session_id, seq=2, action="click", app_name="Finder", element_title="Save")

    steps = client.post(f"{_BASE}/analyze-plan", json={"session_id": session_id}).json()["plan"]["steps"]
    hints = {s["tool_hint"] for s in steps}
    assert "desktop_interact_tool" in hints
    assert "shell_execute" not in hints
