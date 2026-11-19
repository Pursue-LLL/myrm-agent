"""A prompt kept in Chinese and in English says the same thing: the Chinese text names everything the English text names.

[INPUT]
- myrm_agent_harness and app/**/*.py: module-level constants ``X_ZH`` and their English siblings ``X_EN`` or ``X`` (in the
  same module, else in another module of the same directory)

[OUTPUT]
- Fails when a Chinese text leaves out an identifier its English text names (a backticked name, a snake_case word or a
  ``<tag>``: the tool, action, parameter and field names the model has to reproduce exactly), or has a different number
  of headings or code fences. Identifiers only the Chinese text names are fine, since a localised example adds some.
- Fails when a ``_ZH`` constant has no English sibling, and when a registered exception no longer applies: an entry for
  a pair that agrees again, or for a constant that is gone, has to go.

[POS]
tests/architecture/test_prompt_twin_parity.py - the two texts of one prompt are written by hand and change on different
days; this is the check that notices when one version drops a name the other keeps. It compares names and layout, not
meaning: two texts that name the same things can still disagree, and only reading both finds that. It finds a twin by its
``_ZH`` name, so a text a function assembles is outside it, and so are regular expressions and dictionaries, which are
not prompts.
"""

from __future__ import annotations

import ast
import importlib
import re
from functools import cache
from pathlib import Path

import myrm_agent_harness
import pytest

_ROOTS = {
    "myrm_agent_harness": Path(myrm_agent_harness.__file__).resolve().parent,
    "app": Path(__file__).resolve().parents[2] / "app",
}
# 52 pairs of strings exist today; a scan that finds far fewer has gone blind (the suffix renamed, a root moved).
_MIN_COMPARED = 45

# Pairs whose Chinese text lags the English one. An entry fails as stale as soon as the two agree again.
_KNOWN_DRIFT: dict[str, str] = {}
# Pairs the check cannot judge: the Chinese text carries the same rule in other words.
_ACCEPTED = {
    "app.services.kanban.decompose.prompts.SYSTEM_PROMPT_ZH": (
        'the English text quotes "default_assignee"; the Chinese text calls the same fallback 默认 assignee'
    ),
}
_REGISTERED = frozenset(_KNOWN_DRIFT) | frozenset(_ACCEPTED)

# What the model has to reproduce exactly: a backticked span, a <tag>, a snake_case word. The word edges are spelled out
# because a Chinese character is a regex word character, so \b would not separate it from a name written next to it.
_IDENTIFIER_SPAN = re.compile(r"`([^`\n]+)`|<(/?[a-z_]+)>|(?<![A-Za-z0-9_])([a-z]+(?:_[a-z0-9]+)+)(?![A-Za-z0-9_])")
_ARGUMENTS = re.compile(r"(=.*|\(.*|\[.*)$")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def identifiers(text: str) -> set[str]:
    """The names ``text`` mentions, with ``=value``, ``(arguments)`` and ``[index]`` cut off a backticked span."""
    spans = (next(group for group in match.groups() if group) for match in _IDENTIFIER_SPAN.finditer(text))
    return {name for name in (_ARGUMENTS.sub("", span.strip()) for span in spans) if _NAME.fullmatch(name)}


def layout(text: str) -> tuple[int, int]:
    """Number of heading lines and of code fences."""
    return sum(line.startswith("#") for line in text.splitlines()), text.count("```") // 2


def parity_problems(english: str, chinese: str) -> list[str]:
    problems: list[str] = []
    if left_out := sorted(identifiers(english) - identifiers(chinese)):
        problems.append(f"the Chinese text leaves out {left_out}")
    if layout(english) != layout(chinese):
        problems.append(f"(headings, code fences) differ: English {layout(english)}, Chinese {layout(chinese)}")
    return problems


@cache
def _constants(path: Path) -> frozenset[str]:
    """Names assigned at module level in ``path``."""
    names: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return frozenset(names)


def _module(package: str, root: Path, path: Path) -> str:
    parts = [package, *path.relative_to(root).with_suffix("").parts]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _english_sibling(path: Path, name: str) -> tuple[Path, str] | None:
    """The constant holding the English text of ``X_ZH``: ``X_EN`` or ``X``, in ``path`` first, then next to it."""
    base = name.removesuffix("_ZH")
    for module in (path, *sorted(neighbour for neighbour in path.parent.glob("*.py") if neighbour != path)):
        for candidate in (f"{base}_EN", base):
            if candidate in _constants(module):
                return module, candidate
    return None


def _twins() -> dict[str, str | None]:
    """``{module.X_ZH: module.X_EN}`` for every Chinese constant outside the tests; ``None`` where no sibling exists."""
    twins: dict[str, str | None] = {}
    for package, root in _ROOTS.items():
        for path in sorted(root.rglob("*.py")):
            if "tests" in path.relative_to(root).parts or "_ZH" not in path.read_text(encoding="utf-8"):
                continue
            for name in sorted(constant for constant in _constants(path) if constant.endswith("_ZH")):
                sibling = _english_sibling(path, name)
                twins[f"{_module(package, root, path)}.{name}"] = (
                    f"{_module(package, root, sibling[0])}.{sibling[1]}" if sibling else None
                )
    return twins


_TWINS = _twins()


def _constant(qualified_name: str) -> object:
    module, _, name = qualified_name.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _texts(chinese_name: str) -> tuple[str, str] | None:
    """``(English, Chinese)`` of a pair of strings; ``None`` for a pair that is not one (no sibling, a regex, a dict)."""
    english_name = _TWINS[chinese_name]
    if english_name is None:
        return None
    english, chinese = _constant(english_name), _constant(chinese_name)
    return (english, chinese) if isinstance(english, str) and isinstance(chinese, str) else None


def _problems(chinese_name: str) -> list[str]:
    if _TWINS[chinese_name] is None:
        return ["no English sibling: expected the same name with `_EN` in place of `_ZH`, or without the suffix"]
    texts = _texts(chinese_name)
    return parity_problems(*texts) if texts else []


def test_a_name_the_chinese_text_leaves_out_is_reported() -> None:
    assert parity_problems("Pass `since_cursor` or wait_for_input.", "传入 `since_cursor`。") == [
        "the Chinese text leaves out ['wait_for_input']"
    ]


def test_a_name_only_the_chinese_text_has_is_allowed() -> None:
    assert parity_problems("Pass `since_cursor`.", "传入 `since_cursor` 和 `memory_id`。") == []


def test_a_name_written_against_chinese_characters_is_still_found() -> None:
    assert identifiers("使用submit_stdin响应，或<tool_call>标签") == {"submit_stdin", "tool_call"}
    assert parity_problems("Use `submit_stdin`.", "使用submit_stdin响应。") == []


def test_headings_and_code_fences_must_match() -> None:
    english = "# Title\n```\ncode\n```"

    assert parity_problems(english, "# 标题\n```\ncode\n```") == []
    assert parity_problems(english, "标题\n```\ncode\n```") != []
    assert parity_problems(english, "# 标题") != []


def test_the_scan_compares_the_known_twins() -> None:
    compared = [name for name in _TWINS if _texts(name)]

    assert len(compared) >= _MIN_COMPARED, f"only {len(compared)} pairs of strings found; the scan is blind"


@pytest.mark.parametrize("chinese_name", sorted(set(_TWINS) - _REGISTERED))
def test_the_chinese_text_names_what_the_english_text_names(chinese_name: str) -> None:
    problems = _problems(chinese_name)

    assert not problems, f"{chinese_name} against {_TWINS[chinese_name]}: {'; '.join(problems)}"


@pytest.mark.parametrize("chinese_name", sorted(_REGISTERED))
def test_a_registered_pair_still_needs_its_entry(chinese_name: str) -> None:
    assert chinese_name in _TWINS, "no longer a Chinese constant of this tree; drop the entry"
    assert _problems(chinese_name), "the two texts agree now; drop the entry"
