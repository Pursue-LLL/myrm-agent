"""Every test that talks to a real model builds it through ``live_chat_model``, never with ``ChatOpenAI(...)`` itself.

[INPUT]
- tests/**/*.py: every call whose callee is named ``ChatOpenAI``

[OUTPUT]
- Fails when a test module other than ``tests/support/live_chat_model.py`` calls ``ChatOpenAI(...)``. Such a model shares
  langchain-openai's process-wide async HTTP client, whose pooled connections stay bound to the event loop of the first
  test that used them, so the next live test in the same process fails with ``Event loop is closed``. It matches calls
  by name, so a class renamed on import or reached through ``getattr`` is not seen.

[POS]
tests/architecture/test_live_chat_model_single_entry.py - guard for ``tests/support/live_chat_model.py``. The failure it
prevents appears only when two live tests share one pytest process and the provider answers, so a model built directly
looks fine in a single run.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_TESTS_ROOT = _SERVER_ROOT / "tests"
_HELPER = _TESTS_ROOT / "support" / "live_chat_model.py"
_MODEL_CLASS = "ChatOpenAI"


def direct_model_builds(source: str) -> Iterator[int]:
    """Line of each call in *source* that builds a ``ChatOpenAI``; an import or an annotation is not a build."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name == _MODEL_CLASS:
            yield node.lineno


def _builders_outside_the_helper() -> Iterator[str]:
    for path in sorted(_TESTS_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        # Parsing every test module is the slow part; only a module that names the class can call it.
        if path == _HELPER or _MODEL_CLASS not in source:
            continue
        for line in direct_model_builds(source):
            yield f"{path.relative_to(_SERVER_ROOT).as_posix()}:{line}: {_MODEL_CLASS}(...)"


def test_the_helper_is_the_one_place_that_builds_the_model() -> None:
    """An exemption for a helper that no longer builds the model would leave the scan below guarding nothing."""
    assert len(list(direct_model_builds(_HELPER.read_text(encoding="utf-8")))) == 1


def test_no_test_builds_a_chat_model_without_the_helper() -> None:
    offenders = list(_builders_outside_the_helper())

    assert not offenders, (
        "build the model with tests.support.live_chat_model.live_chat_model: a bare ChatOpenAI shares one HTTP client "
        "across the process and fails with 'Event loop is closed' in the second test that uses it:\n" + "\n".join(offenders)
    )


class TestTheScannerSeesWhatItShould:
    def test_a_model_built_by_its_class_name_is_found(self) -> None:
        assert list(direct_model_builds('llm = ChatOpenAI(model="m")')) == [1]

    def test_a_model_built_through_its_module_is_found(self) -> None:
        assert list(direct_model_builds('import langchain_openai\nllm = langchain_openai.ChatOpenAI(model="m")')) == [2]

    def test_an_import_or_an_annotation_is_not_a_build(self) -> None:
        source = "from langchain_openai import ChatOpenAI\n\n\ndef ask(llm: ChatOpenAI) -> None: ...\n"

        assert list(direct_model_builds(source)) == []

    def test_the_helper_call_is_not_a_build(self) -> None:
        source = 'async with live_chat_model(model="m", api_key="k", base_url=None) as llm:\n    ...\n'

        assert list(direct_model_builds(source)) == []
