"""Tests for prebuilt trunk workflows: seed, handoff, gates, admit API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from myrm_agent_harness.agent.dynamic_workflow.template_validation import (
    extract_template_placeholders,
    validate_orchestration_script,
)

from app.services.workflow_templates import service as workflow_templates_service
from app.services.workflow_templates.gates import (
    acceptance_gate,
    evidence_gate,
    safety_gate,
)
from app.services.workflow_templates.handoff import (
    build_handoff,
    to_template_args,
    validate_handoff,
)
from app.services.workflow_templates.trunk_templates import (
    TRUNK_CATALOG_VERSION,
    TRUNK_TEMPLATES,
    describe_trunk_catalog,
    is_trunk_template,
    seed_trunk_templates,
)


def _seeded_store(tmp_path, monkeypatch):
    db_path = tmp_path / "workflow.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        workflow_templates_service,
        "resolve_workflow_db_path",
        lambda: db_path,
    )
    return workflow_templates_service.get_template_store()


def test_trunk_seed_is_idempotent_and_valid(tmp_path, monkeypatch) -> None:
    store = _seeded_store(tmp_path, monkeypatch)
    first = seed_trunk_templates(store)
    second = seed_trunk_templates(store)
    assert len(first) == 5
    assert [record.template_id for record in first] == [record.template_id for record in second]
    assert {record.template_id for record in first} == {
        "trunk-product-triage",
        "trunk-product-delivery",
        "trunk-dev-implement",
        "trunk-bugfix",
        "trunk-product-consolidate",
    }
    for template in TRUNK_TEMPLATES:
        ok, error = validate_orchestration_script(template.script_code)
        assert ok, error
        assert set(extract_template_placeholders(template.script_code)) == set(template.placeholders)
    assert all(record.trust_latch is False for record in first)
    assert TRUNK_CATALOG_VERSION == 1
    assert len(describe_trunk_catalog()) == 5
    assert all(not is_trunk_template("user-saved-flow") for _ in [0])
    assert all(is_trunk_template(record.template_id) for record in first)


def test_seed_never_overwrites_user_edits(tmp_path, monkeypatch) -> None:
    from app.services.workflow_templates.trunk_templates import seed_trunk_templates as seed

    store = _seeded_store(tmp_path, monkeypatch)
    seed(store)
    custom = "import myrm_tools\nmyrm_tools.spawn_subagent(task_id='t', agent_type='generalPurpose', task_description='custom', readonly=True)\n"
    store.save_template(
        template_id="trunk-bugfix",
        display_name="My Custom Bugfix",
        script_code=custom,
        trust_latch=False,
    )
    seed(store)
    record = store.get_template("trunk-bugfix")
    assert record is not None
    assert record.display_name == "My Custom Bugfix"
    assert record.script_code == custom


def test_trunk_catalog_endpoint_lists_five(client: TestClient, tmp_path, monkeypatch) -> None:
    from app.services.workflow_templates.trunk_templates import seed_trunk_templates as seed

    _seeded_store(tmp_path, monkeypatch)
    resp = client.get("/api/v1/workflow-templates/trunk-catalog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert len(body["templates"]) == 5
    assert body["templates"][0]["templateId"] == "trunk-product-triage"

    store = workflow_templates_service.get_template_store()
    seed(store)
    again = client.get("/api/v1/workflow-templates/trunk-catalog")
    assert again.status_code == 200
    assert len(again.json()["templates"]) == 5


def test_admit_merges_handoff_args(client: TestClient, tmp_path, monkeypatch) -> None:
    from app.services.workflow_templates.trunk_templates import seed_trunk_templates as seed

    _seeded_store(tmp_path, monkeypatch)
    seed(workflow_templates_service.get_template_store())
    resp = client.post(
        "/api/v1/workflow-templates/trunk-product-triage/admit",
        json={
            "template_args": {"topic": "Q3", "source_hint": "support inbox"},
            "handoff": {
                "source_flow": "inbox",
                "target_flow": "trunk-product-triage",
                "intent": "Triage Q3 feedback.",
                "materials": [{"title": "Note", "excerpt": "Users complain about login."}],
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["admitted"] is True


def test_handoff_build_validate_and_args() -> None:
    handoff = build_handoff(
        source_flow="trunk-product-triage",
        target_flow="trunk-product-delivery",
        intent="Turn the triage decision into a PRD.",
        materials=[("Decision", "Fix A first, evidence attached."), ("  ", "  ")],
        evidence_refs=["chat-1", ""],
    )
    assert validate_handoff(handoff) == []
    assert len(handoff.materials) == 1
    assert handoff.evidence_refs == ("chat-1",)

    args = to_template_args(handoff, {"topic": "Q3 report"})
    assert args["intent"] == "Turn the triage decision into a PRD."
    assert "Fix A first" in args["context"]
    assert args["topic"] == "Q3 report"

    empty = build_handoff(source_flow="", target_flow="", intent="", materials=[])
    assert validate_handoff(empty) == ["source_flow", "target", "intent", "materials"]


def test_gates_cover_all_paths(tmp_path, monkeypatch) -> None:
    store = _seeded_store(tmp_path, monkeypatch)
    seed_trunk_templates(store)
    record = store.get_template("trunk-bugfix")
    assert record is not None

    assert safety_gate(None, None).reason_code == "TEMPLATE_NOT_FOUND"
    assert safety_gate(record, {"stack_trace": "x"}).reason_code == "ARGS_INVALID"
    assert safety_gate(record, {"error_report": "boom", "stack_trace": "line 1"}).ok

    bad = build_handoff(source_flow="a", target_flow="", intent="", materials=[])
    assert evidence_gate(bad).reason_code == "EVIDENCE_MISSING"
    good = build_handoff(source_flow="a", target_flow="b", intent="fix it", materials=[("M", "text")])
    assert evidence_gate(good).ok

    assert acceptance_gate([], "anything").reason_code == "CRITERIA_MISSING"
    assert acceptance_gate(["login works", "no crash"], "Login works now.").reason_code == "CRITERIA_UNMET"
    assert acceptance_gate(["login works"], "Login works now.").ok


def test_admit_api_end_to_end(client: TestClient, tmp_path, monkeypatch) -> None:
    store = _seeded_store(tmp_path, monkeypatch)
    seed_trunk_templates(store)
    base = "/api/v1/workflow-templates/trunk-bugfix/admit"

    missing = client.post(base, json={"template_args": {}})
    assert missing.status_code == 422
    assert missing.json()["detail"]["reason_code"] == "ARGS_INVALID"

    unknown = client.post("/api/v1/workflow-templates/nope/admit", json={})
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["reason_code"] == "TEMPLATE_NOT_FOUND"

    thin = client.post(
        base,
        json={
            "template_args": {"error_report": "boom", "stack_trace": "line 1"},
            "handoff": {"source_flow": "a", "target_flow": "", "intent": "", "materials": []},
        },
    )
    assert thin.status_code == 422
    assert thin.json()["detail"]["reason_code"] == "EVIDENCE_MISSING"

    unmet = client.post(
        base,
        json={
            "template_args": {"error_report": "boom", "stack_trace": "line 1"},
            "prior_criteria": ["login works"],
            "prior_deliverable": "Something unrelated.",
        },
    )
    assert unmet.status_code == 422
    assert unmet.json()["detail"]["reason_code"] == "CRITERIA_UNMET"

    admitted = client.post(
        base,
        json={
            "template_args": {"error_report": "boom", "stack_trace": "line 1"},
            "handoff": {
                "source_flow": "trunk-product-triage",
                "target_flow": "trunk-bugfix",
                "intent": "Fix the crash.",
                "materials": [{"title": "Report", "excerpt": "It crashes on login."}],
            },
            "prior_criteria": ["login works"],
            "prior_deliverable": "Login works now.",
        },
    )
    assert admitted.status_code == 200
    body = admitted.json()
    assert body["admitted"] is True
    assert body["reasonCode"] == "ADMITTED"

    # Frontend contract: camelCase aliases must also be accepted.
    camel = client.post(
        base,
        json={
            "templateArgs": {"error_report": "boom", "stack_trace": "line 1"},
            "handoff": {
                "sourceFlow": "trunk-product-triage",
                "targetFlow": "trunk-bugfix",
                "intent": "Fix the crash.",
                "materials": [{"title": "Report", "excerpt": "It crashes on login."}],
                "evidenceRefs": ["chat-1"],
            },
            "priorCriteria": ["login works"],
            "priorDeliverable": "Login works now.",
        },
    )
    assert camel.status_code == 200
    assert camel.json()["reasonCode"] == "ADMITTED"


def test_list_marks_trunk_templates(client: TestClient, tmp_path, monkeypatch) -> None:
    _seeded_store(tmp_path, monkeypatch)
    resp = client.get("/api/v1/workflow-templates")
    assert resp.status_code == 200
    assert resp.json()["templates"] == []
    from app.services.workflow_templates.trunk_templates import seed_trunk_templates as seed

    seed(workflow_templates_service.get_template_store())
    resp = client.get("/api/v1/workflow-templates")
    flagged = {item["templateId"]: item["isTrunk"] for item in resp.json()["templates"]}
    assert flagged.get("trunk-bugfix") is True
