"""Every chat-model call in the server is either behind the outbound privacy guard or accounted for here.

The guard sits inside the harness's ChatLiteLLM, so a server module that talks to litellm's chat API directly reaches
the provider with whatever text it was given, privacy policy or not. A new direct call must be a conscious decision:
route it through ChatLiteLLM, mask its text with ``sanitize_outbound_text``, or be listed below with the reason it
carries no conversation text.
"""

from __future__ import annotations

import ast
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"
_CHAT_CALLS = frozenset({"completion", "acompletion", "responses", "aresponses", "text_completion", "atext_completion"})

# file -> why the text it sends is outside the privacy guard's scope
_OUT_OF_SCOPE: dict[str, str] = {
    "channels/voice/tts.py": (
        "voice output pipeline: the reply text goes on to the speech provider, and speech synthesis is a declared "
        "non-chat call outside the privacy scope"
    ),
    "api/security/generate.py": (
        "the plain-language rule text the user typed to have it turned into a security rule; masking it would corrupt the rule"
    ),
}
# file -> why it is covered; the file must still call sanitize_outbound_text
_MASKED_FIRST: dict[str, str] = {
    "services/skill_optimization/semantic_comparator.py": "the judged tool outputs are masked before the judge sees them",
}


def direct_chat_call_lines(source: str) -> list[int]:
    """Line numbers of calls to litellm's chat API: ``litellm.acompletion(...)`` or an imported ``acompletion(...)``."""
    tree = ast.parse(source)
    modules: set[str] = set()
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.asname or alias.name for alias in node.names if alias.name == "litellm")
        elif isinstance(node, ast.ImportFrom) and node.module == "litellm":
            functions.update(alias.asname or alias.name for alias in node.names if alias.name in _CHAT_CALLS)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_module_call = (
            isinstance(func, ast.Attribute)
            and func.attr in _CHAT_CALLS
            and isinstance(func.value, ast.Name)
            and func.value.id in modules
        )
        if is_module_call or (isinstance(func, ast.Name) and func.id in functions):
            lines.append(node.lineno)
    return lines


def _files_with_direct_chat_calls() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in _APP_ROOT.rglob("*.py"):
        lines = direct_chat_call_lines(path.read_text(encoding="utf-8"))
        if lines:
            found[path.relative_to(_APP_ROOT).as_posix()] = lines
    return found


def test_the_detector_finds_each_way_of_calling_litellm_directly() -> None:
    assert direct_chat_call_lines("import litellm\nawait litellm.acompletion(model='m')") == [2]
    assert direct_chat_call_lines("import litellm as ll\nll.completion(model='m')") == [2]
    assert direct_chat_call_lines("from litellm import acompletion\nawait acompletion(model='m')") == [2]
    assert direct_chat_call_lines("from litellm import aresponses as send\nawait send(model='m')") == [2]


def test_the_detector_ignores_everything_that_is_not_litellm_chat() -> None:
    assert direct_chat_call_lines("import litellm\nawait litellm.aembedding(model='m')") == []
    assert direct_chat_call_lines("client.responses(model='m')") == []
    assert direct_chat_call_lines("class P:\n    async def acompletion(self): ...") == []
    assert direct_chat_call_lines("from other import acompletion\nawait acompletion()") == []


def test_every_direct_chat_call_is_accounted_for() -> None:
    accounted = _OUT_OF_SCOPE.keys() | _MASKED_FIRST.keys()
    unaccounted = {rel: lines for rel, lines in _files_with_direct_chat_calls().items() if rel not in accounted}

    assert not unaccounted, (
        f"Direct litellm chat calls bypass the outbound privacy guard: {unaccounted}. Use ChatLiteLLM, mask the text "
        "with sanitize_outbound_text, or list the file in _OUT_OF_SCOPE with the reason it carries no conversation text."
    )


def test_the_accounted_files_still_make_the_call_they_are_listed_for() -> None:
    found = _files_with_direct_chat_calls()
    stale = sorted(rel for rel in _OUT_OF_SCOPE.keys() | _MASKED_FIRST.keys() if rel not in found)

    assert not stale, f"Remove from the allowlist, they no longer call litellm chat directly: {stale}"


def test_a_file_listed_as_masked_first_calls_the_mask() -> None:
    unmasked = sorted(rel for rel in _MASKED_FIRST if "sanitize_outbound_text" not in (_APP_ROOT / rel).read_text("utf-8"))

    assert not unmasked, f"Listed as masked first but never calls sanitize_outbound_text: {unmasked}"


def test_every_allowlist_entry_gives_its_reason() -> None:
    assert all(reason.strip() for reason in (_OUT_OF_SCOPE | _MASKED_FIRST).values())
