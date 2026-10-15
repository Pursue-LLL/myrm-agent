"""Architecture test: the entries listed here screen the text a user typed before they store or deliver it.

A secret that gets past one entry is stored (a cron prompt, a task card) or delivered (a steer) as if no rule existed.
Each entry below must call the gate that fits it, and every gate must end in ``screen_user_text``, the single place
that decides, records and fails closed. An endpoint that accepts task-instruction text of a user belongs in this table:
a scan of the write endpoints finds the ones whose request carries an instruction-like field, and each of them is either
an entry or an exemption with the reason its text is not one an agent is going to follow.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parents[2] / "app"

# (file under app/, function that receives the text, the gate it must call)
_ENTRIES: tuple[tuple[str, str, str], ...] = (
    ("services/agent/stream_session/orchestrator.py", "run_agent_stream", "check_stream_risk"),
    ("api/agents/general_agent/streaming.py", "steer_agent", "_risk_refusal"),
    ("api/agents/general_agent/streaming.py", "redirect_agent", "_risk_refusal"),
    ("api/agents/subagents.py", "steer_subagent", "reject_if_risky"),
    ("api/background_tasks/router.py", "steer_background_task", "reject_if_risky"),
    ("api/cron/routes/jobs.py", "create_job", "reject_if_risky"),
    ("api/cron/routes/jobs.py", "update_job", "reject_if_risky"),
    ("api/cron/routes/heartbeat.py", "heartbeat_enable", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "create_task", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "update_task", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "move_task", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "reject_task", "reject_if_risky"),
    ("api/kanban/routes/tasks.py", "reclaim_task", "reject_if_risky"),
    ("api/kanban/routes/task_meta.py", "add_comment", "reject_if_risky"),
    ("api/goals/constraints.py", "update_goal_constraints", "reject_if_risky"),
    ("api/goals/constraints.py", "update_goal_objective", "reject_if_risky"),
    ("api/goals/router.py", "add_goal_subgoal", "reject_if_risky"),
    ("api/goals/router.py", "draft_goal", "reject_if_risky"),
    ("api/agents/agent.py", "_reject_risky_profile_text", "reject_if_risky"),
    ("api/agents/agent.py", "create_agent", "_reject_risky_profile_text"),
    ("api/agents/agent.py", "update_agent", "_reject_risky_profile_text"),
    ("api/agents/generate_prompt.py", "generate_prompt", "reject_if_risky"),
    ("api/agents/ai_build.py", "ai_build", "reject_if_risky"),
    ("api/batch_directory/router.py", "create_project", "reject_if_risky"),
    ("api/skills/evolution/derive.py", "derive_skill", "reject_if_risky"),
    ("core/cron/adapters/inbound_event_dispatch.py", "dispatch_cron_event_for_inbound_message", "screen_user_text"),
    ("channels/routing/router.py", "_consume_loop", "hold_risky_inbound"),
    ("channels/routing/router.py", "_dispatch_resolved", "hold_risky_inbound"),
    ("channels/routing/router.py", "_handle_merged", "hold_risky_inbound"),
)

# Each gate is a thin wrapper that must end in the one screening entry.
_WRAPPERS: tuple[tuple[str, str], ...] = (
    ("services/agent/stream_session/risk_gate.py", "check_stream_risk"),
    ("api/agents/general_agent/streaming.py", "_risk_refusal"),
    ("services/risk/refusal.py", "reject_if_risky"),
    ("channels/routing/inbound_risk_gate.py", "hold_risky_inbound"),
)
_SCREEN = "screen_user_text"

# Request fields whose text a model goes on to follow. A write endpoint that carries one is an entry above or is listed
# here with the reason its text is not for an agent to follow (file under app/, function) -> reason.
_INSTRUCTION_FIELDS = frozenset({"prompt", "instruction", "intent", "objective", "goal"})
_EXEMPT: dict[tuple[str, str], str] = {
    (
        "api/channels/bitable_copilot_router.py",
        "wrangle_table_data",
    ): "the engine rewrites cells by deterministic rules; no model reads the instruction",
    (
        "api/chats/chat/turn.py",
        "regenerate_last_turn",
    ): "echoes the instruction back; the client sends it as a chat turn, which run_agent_stream screens",
    (
        "api/cron/routes/prerequisite.py",
        "check_prerequisite",
    ): "uses the prompt only as a lookup key to count earlier successful runs; nothing stores or sends it",
    ("api/media/batch_routes.py", "create_batch_job"): "prompts for an image generator, not instructions an agent follows",
    (
        "api/skills/desktop_recorder/router.py",
        "compile_desktop_plan",
    ): "compiles a recorded plan into SKILL.md text and returns it; nothing is stored or sent to a model",
    (
        "api/workflow_templates/router.py",
        "admit_template_run",
    ): "returns an admission decision from the trunk gates; the text is neither stored nor sent to a model",
}


def _is_name(node: ast.expr, name: str) -> bool:
    return (isinstance(node, ast.Name) and node.id == name) or (isinstance(node, ast.Attribute) and node.attr == name)


def function_calls(source: str, function: str, callee: str) -> bool | None:
    """Whether *function* in *source* calls *callee*; None when the source defines no such function."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function:
            return any(isinstance(n, ast.Call) and _is_name(n.func, callee) for n in ast.walk(node))
    return None


def _source(relative_path: str) -> str:
    return (_APP / relative_path).read_text(encoding="utf-8")


def test_detector_sees_a_call_and_a_missing_call_and_a_missing_function() -> None:
    source = "async def a(x):\n    await gate(x)\n\nasync def b(x):\n    return x\n\nclass C:\n    def m(self):\n        self.gate(1)\n"
    assert function_calls(source, "a", "gate") is True
    assert function_calls(source, "b", "gate") is False
    assert function_calls(source, "m", "gate") is True
    assert function_calls(source, "missing", "gate") is None


@pytest.mark.architecture
@pytest.mark.parametrize(("relative_path", "function", "gate"), _ENTRIES, ids=[f"{p}::{f}" for p, f, _ in _ENTRIES])
def test_entry_screens_user_text_before_acting_on_it(relative_path: str, function: str, gate: str) -> None:
    called = function_calls(_source(relative_path), function, gate)

    assert called is not None, f"{relative_path} no longer defines {function}; update the table in this test"
    assert called, f"{relative_path}::{function} must call {gate} on the text a user typed (see services/risk/refusal.py)"


@pytest.mark.architecture
@pytest.mark.parametrize(("relative_path", "function"), _WRAPPERS, ids=[f"{p}::{f}" for p, f in _WRAPPERS])
def test_gate_ends_in_the_single_screening_entry(relative_path: str, function: str) -> None:
    assert function_calls(_source(relative_path), function, _SCREEN), (
        f"{relative_path}::{function} must call {_SCREEN}, the only place that detects, records and fails closed"
    )


# --- completeness: every write endpoint that carries instruction text is an entry or an exemption -----------------


def _is_write_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("post", "put", "patch")
        for d in node.decorator_list
    )


def _annotation_names(annotation: ast.expr) -> tuple[bool, set[str]]:
    """Whether the annotation names ``str``, and the capitalised names in it that may be request models."""
    text = ast.unparse(annotation)
    return bool(re.search(r"\bstr\b", text)), set(re.findall(r"\b[A-Z]\w*", text))


type _ModelIndex = dict[str, tuple[set[str], dict[str, ast.expr]]]


def _model_index(sources: Mapping[str, str]) -> _ModelIndex:
    """Every class by name: its base class names and its annotated fields. Same-named classes are merged."""
    index: _ModelIndex = {}
    for source in sources.values():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ClassDef):
                bases, fields = index.setdefault(node.name, (set(), {}))
                bases.update(b.id for b in node.bases if isinstance(b, ast.Name))
                fields.update(
                    {
                        s.target.id: s.annotation
                        for s in node.body
                        if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
                    }
                )
    return index


def _text_fields(model: str, index: _ModelIndex, seen: frozenset[str] = frozenset()) -> set[str]:
    """Names of the string fields a request model carries, nested models and base classes included."""
    if model in seen or model not in index:
        return set()
    bases, fields = index[model]
    seen |= {model}
    names: set[str] = set()
    for base in bases:
        names |= _text_fields(base, index, seen)
    for field, annotation in fields.items():
        is_str, referenced = _annotation_names(annotation)
        if is_str:
            names.add(field)
        for name in referenced:
            names |= _text_fields(name, index, seen)
    return names


def instruction_text_handlers(api_sources: Mapping[str, str], model_sources: Mapping[str, str]) -> set[tuple[str, str]]:
    """(path, function) of every write endpoint whose request carries an instruction-like text field."""
    index = _model_index(model_sources)
    found: set[tuple[str, str]] = set()
    for path, source in api_sources.items():
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or not _is_write_route(node):
                continue
            names: set[str] = set()
            for arg in (*node.args.args, *node.args.kwonlyargs):
                if arg.annotation is None:
                    continue
                is_str, referenced = _annotation_names(arg.annotation)
                if is_str:
                    names.add(arg.arg)
                for name in referenced:
                    names |= _text_fields(name, index)
            if names & _INSTRUCTION_FIELDS:
                found.add((path, node.name))
    return found


@cache
def _repository_handlers() -> frozenset[tuple[str, str]]:
    def read(directory: Path, needle: str = "") -> dict[str, str]:
        files = {str(p.relative_to(_APP)): p.read_text(encoding="utf-8") for p in directory.rglob("*.py")}
        return {path: text for path, text in files.items() if needle in text}

    return frozenset(instruction_text_handlers(read(_APP / "api"), read(_APP, "BaseModel")))


def test_scan_finds_fields_through_nesting_inheritance_and_plain_parameters() -> None:
    models = {
        "m.py": (
            "class Base(BaseModel):\n    goal: str\n"
            "class Body(Base):\n    note: str\n"
            "class Wrapper(BaseModel):\n    inner: Body | None\n"
            "class Plain(BaseModel):\n    title: str\n    size: int\n"
        )
    }
    api = {
        "a.py": (
            "@router.post('')\nasync def inherited(body: Body): ...\n"
            "@router.put('/x')\nasync def nested(body: Wrapper): ...\n"
            "@router.patch('/y')\nasync def plain_param(prompt: str): ...\n"
            "@router.post('/z')\nasync def no_instruction(body: Plain): ...\n"
            "@router.get('/g')\nasync def read_only(prompt: str): ...\n"
        )
    }

    assert instruction_text_handlers(api, models) == {("a.py", "inherited"), ("a.py", "nested"), ("a.py", "plain_param")}


@pytest.mark.architecture
def test_every_instruction_text_endpoint_is_an_entry_or_an_exemption() -> None:
    entries = {(path, function) for path, function, _ in _ENTRIES}
    unregistered = sorted(h for h in _repository_handlers() if h not in entries and h not in _EXEMPT)

    assert not unregistered, (
        "These write endpoints take instruction-like text a model will follow but do not screen it. Call the gate "
        "(services/risk/refusal.py::reject_if_risky) and add the endpoint to _ENTRIES, or add it to _EXEMPT with the "
        f"reason its text is not for an agent to follow: {unregistered}"
    )


@pytest.mark.architecture
def test_exemptions_name_endpoints_that_still_carry_instruction_text() -> None:
    entries = {(path, function) for path, function, _ in _ENTRIES}
    stale = sorted(k for k in _EXEMPT if k not in _repository_handlers())
    gated_and_exempt = sorted(k for k in _EXEMPT if k in entries)

    assert not stale, f"These exemptions match no write endpoint with instruction text; remove them: {stale}"
    assert not gated_and_exempt, f"These endpoints are both an entry and an exemption: {gated_and_exempt}"
