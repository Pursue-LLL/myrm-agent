"""Architecture guard: every LangChain-family package pyproject.toml declares has a floor and an upper bound.

The agent is built on LangChain and LangGraph. A floor says which release the code was written against and the weekly
canary (``harness-framework-canary.yml``) installs exactly that release; an upper bound keeps an untested major
release out of a user's environment. ``scripts/framework_requirements.py`` reads both and is what the canary installs,
so the rule here and the versions the canary tests are one declaration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.framework_requirements import floor_of, framework_requirements, has_upper_bound, problems

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _pyproject(*dependencies: str, extra: tuple[str, ...] = ()) -> str:
    quoted = ", ".join(f'"{d}"' for d in dependencies)
    quoted_extra = ", ".join(f'"{d}"' for d in extra)
    return f'[project]\nname = "x"\ndependencies = [{quoted}]\n[project.optional-dependencies]\nretrieval = [{quoted_extra}]\n'


@pytest.mark.architecture
def test_every_framework_package_declares_a_floor_and_an_upper_bound() -> None:
    requirements = framework_requirements(_PYPROJECT.read_text(encoding="utf-8"))

    assert {r.name for r in requirements} >= {"langchain", "langchain-core", "langgraph", "langgraph-checkpoint-sqlite"}
    assert problems(requirements) == []


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (_pyproject("langchain>=1.4.3"), ["langchain must declare a '<' upper bound, found '>=1.4.3'"]),
        (_pyproject("langgraph<2"), ["langgraph must declare exactly one '>=' floor, found '<2'"]),
        (
            _pyproject("pydantic>=2", extra=("langchain-text-splitters>=1.1.3",)),
            ["langchain-text-splitters must declare a '<' upper bound, found '>=1.1.3'"],
        ),
        (_pyproject("langchain>=1.4.3,<2", "langchain-core>=1.6.6,<2"), []),
        # A package that only mentions LangChain in its name is another project's dependency, not the framework.
        (_pyproject("openinference-instrumentation-langchain>=0.1.78"), []),
    ],
)
def test_the_rule_names_each_package_that_breaks_it(text: str, expected: list[str]) -> None:
    assert problems(framework_requirements(text)) == expected


@pytest.mark.architecture
def test_floor_and_bound_are_read_from_the_requirement() -> None:
    [requirement] = framework_requirements(_pyproject("langgraph>=1.2.13,<2"))

    assert floor_of(requirement) == "1.2.13"
    assert has_upper_bound(requirement)
