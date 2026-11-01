"""Every chat-model call is either behind the outbound privacy guard or accounted for here.

The guard sits inside TransportChatModel (``toolkits/llms``), so any module that reaches the provider through the model
transport directly (``get_transport()``) or through the one-shot ``acomplete_text`` helper sends whatever text it was
given, privacy policy or not. A new direct call must be a conscious decision: route it through TransportChatModel, mask
its text with ``sanitize_outbound_text``, or be listed below with the reason it carries no user text.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src" / "myrm_agent_harness"
_DIRECT_ENTRY_POINTS = frozenset({"get_transport", "acomplete_text"})
_GUARDED_PACKAGE = "toolkits/llms/"

# file -> why the text it sends is not the user's conversation
_NO_USER_TEXT: dict[str, str] = {
    "eval/judge_call.py": "LLM judge of developer-run evals over fixture outputs; never part of a user session",
}


def direct_model_call_lines(source: str) -> list[int]:
    """Line numbers of calls to ``get_transport()`` or ``acomplete_text(...)``, bare or through a module."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name in _DIRECT_ENTRY_POINTS:
            lines.append(node.lineno)
    return lines


def _files_with_direct_model_calls() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if rel.startswith(_GUARDED_PACKAGE):
            continue
        lines = direct_model_call_lines(path.read_text(encoding="utf-8"))
        if lines:
            found[rel] = lines
    return found


def test_the_detector_finds_each_way_of_reaching_a_provider_directly() -> None:
    assert direct_model_call_lines("await get_transport().acompletion(model='m')") == [1]
    assert direct_model_call_lines("client = transport.get_transport()\nclient.completion(model='m')") == [1]
    assert direct_model_call_lines("text = await acomplete_text('m', messages)") == [1]
    assert direct_model_call_lines("text = await text_completion.acomplete_text('m', messages)") == [1]


def test_the_detector_ignores_everything_that_is_not_a_direct_model_call() -> None:
    assert direct_model_call_lines("from x import get_transport, acomplete_text") == []
    assert direct_model_call_lines("client.responses(model='m')") == []
    assert direct_model_call_lines("class P:\n    async def acompletion(self): ...") == []
    assert direct_model_call_lines("await create_chat_model('m').ainvoke(messages)") == []


def test_every_direct_model_call_is_accounted_for() -> None:
    unaccounted = {rel: lines for rel, lines in _files_with_direct_model_calls().items() if rel not in _NO_USER_TEXT}

    assert not unaccounted, (
        f"Direct model calls bypass the outbound privacy guard: {unaccounted}. "
        "Use TransportChatModel, mask the text with sanitize_outbound_text, or list the file in _NO_USER_TEXT with the reason it carries no user text."
    )


def test_the_accounted_files_still_make_the_call_they_are_listed_for() -> None:
    found = _files_with_direct_model_calls()
    stale = sorted(rel for rel in _NO_USER_TEXT if rel not in found)

    assert not stale, f"Remove from the allowlist, they no longer call the model transport directly: {stale}"


def test_every_allowlist_entry_gives_its_reason() -> None:
    assert all(reason.strip() for reason in _NO_USER_TEXT.values())
