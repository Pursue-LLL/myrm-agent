"""Architecture guard: the harness never rewrites an object that LangChain or LangGraph owns.

The agent is a LangChain graph, and every point where our code changes one of its objects in place (a method swapped on
a model instance, a class patched, ``__class__`` reassigned) ties the harness to how the framework happens to call that
object today: the next minor release can stop calling it that way and nothing fails until a run misbehaves. What the
framework offers instead is public and versioned: a middleware hook, ``ModelRequest.override`` or
``ToolCallRequest.override``. The scanner below flags the three forms, and the tests pin it on source snippets, so a
scanner that stops seeing them cannot pass for a clean tree.
"""

from __future__ import annotations

import ast
from collections.abc import Collection
from pathlib import Path

import pytest
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode
from langgraph.pregel import Pregel

_HARNESS_SRC = Path(__file__).resolve().parent.parent.parent / "src" / "myrm_agent_harness"
_FRAMEWORK_PACKAGES = ("langchain", "langgraph", "langsmith")
_OWN_OBJECT_NAMES = frozenset({"self", "cls"})

# Every method the framework calls on a model, a tool, a middleware or a graph: swapping one of these on an object that
# is not our own changes what the framework runs. Read from the classes so that a release that adds a hook extends it.
FRAMEWORK_METHODS = frozenset(
    name
    for framework_class in (BaseChatModel, Runnable, BaseTool, AgentMiddleware, ToolNode, Pregel)
    for name in dir(framework_class)
    if not name.startswith("__") and callable(getattr(framework_class, name, None))
)


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _framework_names(tree: ast.AST) -> set[str]:
    """The local names this module binds to something imported from LangChain, LangGraph or LangSmith."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(_FRAMEWORK_PACKAGES):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(
                (alias.asname or alias.name).split(".")[0]
                for alias in node.names
                if alias.name.startswith(_FRAMEWORK_PACKAGES)
            )
    return names


def _attribute_targets(node: ast.AST) -> list[ast.Attribute]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AugAssign | ast.AnnAssign):
        targets = [node.target]
    else:
        return []
    return [target for target in targets if isinstance(target, ast.Attribute)]


def _assignment_problem(
    target: ast.Attribute, framework_names: Collection[str], methods: Collection[str]
) -> str | None:
    root = _root_name(target)
    if target.attr == "__class__":
        return "reassigns __class__"
    if root in framework_names:
        return "assigns an attribute of an imported framework name"
    if target.attr in methods and root not in _OWN_OBJECT_NAMES:
        return f"replaces the framework method {target.attr!r} of another object"
    return None


def _setattr_problem(call: ast.Call, methods: Collection[str]) -> str | None:
    function = call.func
    is_setattr = (isinstance(function, ast.Name) and function.id == "setattr") or (
        isinstance(function, ast.Attribute) and function.attr == "__setattr__" and _root_name(function) == "object"
    )
    if not is_setattr or len(call.args) < 2:
        return None
    target, name = call.args[0], call.args[1]
    if isinstance(name, ast.Constant) and name.value in methods and _root_name(target) not in _OWN_OBJECT_NAMES:
        return f"replaces the framework method {name.value!r} of another object"
    return None


def find_framework_patches(source: str, methods: Collection[str] = FRAMEWORK_METHODS) -> list[tuple[int, str]]:
    """Line and kind of each in-place rewrite of a framework object in *source*."""
    tree = ast.parse(source)
    framework_names = _framework_names(tree)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for target in _attribute_targets(node):
            problem = _assignment_problem(target, framework_names, methods)
            if problem:
                found.append((node.lineno, f"{ast.unparse(target)}: {problem}"))
        if isinstance(node, ast.Call):
            problem = _setattr_problem(node, methods)
            if problem:
                found.append((node.lineno, f"{ast.unparse(node)}: {problem}"))
    return sorted(found)


@pytest.mark.architecture
def test_harness_source_rewrites_no_framework_object() -> None:
    """Replace the patch with a public hook: a middleware, ``request.override(...)``, or a subclass."""
    violations = [
        f"  - {path.relative_to(_HARNESS_SRC).as_posix()}:{line} {what}"
        for path in sorted(_HARNESS_SRC.rglob("*.py"))
        for line, what in find_framework_patches(path.read_text(encoding="utf-8"))
    ]
    assert not violations, "In-place rewrite of a LangChain/LangGraph object:\n" + "\n".join(violations)


@pytest.mark.architecture
@pytest.mark.parametrize(
    "source",
    [
        # The shape the agent once used to pass ``parallel_tool_calls`` to ``bind_tools``.
        "wrapped = copy.copy(llm)\nobject.__setattr__(wrapped, 'bind_tools', patched)\n",
        "setattr(model, 'invoke', patched)\n",
        "model.bind_tools = patched\n",
        "instance.__class__ = Subclass\n",
        "from langgraph.prebuilt import ToolNode\nToolNode._run_one = patched\n",
        "from langchain_core.tools import BaseTool\nBaseTool.tool_call_schema = property(patched)\n",
        "import langgraph.prebuilt.tool_node as tool_node\ntool_node.ToolNode = Replacement\n",
        "from langchain_core.language_models import BaseChatModel as Model\nModel.cache = True\n",
    ],
)
def test_the_scanner_sees_each_form_of_rewrite(source: str) -> None:
    assert find_framework_patches(source)


@pytest.mark.architecture
@pytest.mark.parametrize(
    "source",
    [
        "object.__setattr__(self, 'bind_tools', patched)\n",
        "self.invoke = patched\n",
        "object.__setattr__(self, 'chunk_hash', digest)\n",
        "object.__setattr__(skill, 'usage_stats', stats)\n",
        "setattr(job, name, getattr(latest, name))\n",
        "result.metadata = metadata\n",
        "from langchain_core.messages import AIMessage\nmessage = AIMessage(content='')\nmessage.id = 'a'\n",
        "from langgraph.types import Command\nupdate = Command(update={})\nupdate.metadata = {}\n",
    ],
)
def test_the_scanner_leaves_the_harness_own_objects_alone(source: str) -> None:
    assert find_framework_patches(source) == []
