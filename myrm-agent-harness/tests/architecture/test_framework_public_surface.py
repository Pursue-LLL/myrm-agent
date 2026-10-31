"""Architecture guard: the harness touches LangChain and LangGraph only through what they publish.

The agent is a LangChain graph. Whatever our code reaches that the framework does not publish (an object rewritten in
place, a name outside a module's ``__all__``, a private config key) ties the harness to how the framework happens to
work today: the next minor release can move or change it and nothing fails until a run misbehaves. What the framework
offers instead is public and versioned: a middleware hook, ``ModelRequest.override``, ``ToolCallRequest.override``, the
names a module lists in ``__all__``.

Three scanners hold ``src/`` to that, and each is pinned on source snippets so a scanner that stops seeing its form
cannot pass for a clean tree:

1. In-place rewrites of framework objects: a method swapped on a model instance, a patched class, ``__class__``.
2. Imports: no private module or name, and a name must be listed in its module's ``__all__``. A module that declares no
   ``__all__`` is accepted only when it is in ``DOCUMENTED_MODULES_WITHOUT_ALL``, so a new one is a reviewed choice.
3. Private config keys: a string literal starting with ``__pregel`` or ``__langgraph`` is the framework's runtime
   wiring, not an interface.

Not covered: attribute access on an object the framework hands us, and keys assembled at run time.
"""

from __future__ import annotations

import ast
import importlib
from collections.abc import Callable, Collection
from functools import cache
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
_PRIVATE_KEY_PREFIXES = ("__pregel", "__langgraph")

# Every method the framework calls on a model, a tool, a middleware or a graph: swapping one of these on an object that
# is not our own changes what the framework runs. Read from the classes so that a release that adds a hook extends it.
FRAMEWORK_METHODS = frozenset(
    name
    for framework_class in (BaseChatModel, Runnable, BaseTool, AgentMiddleware, ToolNode, Pregel)
    for name in dir(framework_class)
    if not name.startswith("__") and callable(getattr(framework_class, name, None))
)

# Modules the frameworks document as the place to import from although they declare no ``__all__``.
DOCUMENTED_MODULES_WITHOUT_ALL = frozenset(
    {
        "langchain_core.callbacks.manager",
        "langchain_core.language_models.chat_models",
        "langchain_core.messages.ai",
        "langchain_core.messages.content",
        "langchain_core.messages.tool",
        "langchain_core.runnables.config",
        "langchain_core.tools.convert",
        "langchain_core.utils.function_calling",
        "langchain_core.utils.json",
        "langchain_core.utils.pydantic",
        "langgraph.checkpoint.base",
        "langgraph.checkpoint.memory",
        "langgraph.checkpoint.serde.base",
        "langgraph.checkpoint.sqlite.aio",
        "langgraph.config",
    }
)

# Private keys still read, by file under ``src/`` and with the reason no public replacement exists yet. Delete the entry
# when the read goes: the test below fails for an entry that no longer matches the file.
KNOWN_PRIVATE_KEYS: dict[str, frozenset[str]] = {
    # ``dispatch_custom_event`` takes the config of a run explicitly, and background tasks pass the one they captured;
    # ``langgraph.config.get_stream_writer()`` reads only the config of the current context and takes no argument.
    "utils/event_utils.py": frozenset({"__pregel_runtime"}),
}

PublishedNames = Callable[[str], Collection[str] | None]


@cache
def _parse(source: str) -> ast.Module:
    """One syntax tree per source: the scanners only read it, and the tree of ``src/`` is walked by several of them."""
    return ast.parse(source)


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
    tree = _parse(source)
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


def _published_names(module: str) -> frozenset[str] | None:
    """What *module* lists in ``__all__``, or ``None`` when it declares no list."""
    exported = getattr(importlib.import_module(module), "__all__", None)
    return None if exported is None else frozenset(exported)


def _has_private_segment(module: str) -> bool:
    return any(part.startswith("_") for part in module.split("."))


def _import_problem(module: str, name: str, published: PublishedNames, documented: Collection[str]) -> str | None:
    statement = f"from {module} import {name}"
    if _has_private_segment(module) or name.startswith("_"):
        return f"{statement}: private"
    try:
        names = published(module)
    except ImportError:
        return f"{statement}: the module cannot be imported here"
    if names is None:
        return None if module in documented else f"{statement}: the module declares no __all__ and is not documented"
    return None if name in names else f"{statement}: not listed in the module's __all__"


def find_non_public_imports(
    source: str,
    published: PublishedNames = _published_names,
    documented: Collection[str] = DOCUMENTED_MODULES_WITHOUT_ALL,
) -> list[tuple[int, str]]:
    """Line and kind of each import of a framework name that the framework does not publish."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(_parse(source)):
        if isinstance(node, ast.Import):
            found.extend(
                (node.lineno, f"import {alias.name}: private")
                for alias in node.names
                if alias.name.startswith(_FRAMEWORK_PACKAGES) and _has_private_segment(alias.name)
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and not node.level
            and node.module.startswith(_FRAMEWORK_PACKAGES)
        ):
            for alias in node.names:
                problem = _import_problem(node.module, alias.name, published, documented)
                if problem:
                    found.append((node.lineno, problem))
    return sorted(found)


def find_private_framework_keys(source: str) -> list[tuple[int, str]]:
    """Line and text of each string literal that names a private key of the framework."""
    return sorted(
        (node.lineno, node.value)
        for node in ast.walk(_parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith(_PRIVATE_KEY_PREFIXES)
    )


@cache
def _source_files() -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.relative_to(_HARNESS_SRC).as_posix(), path.read_text(encoding="utf-8"))
        for path in sorted(_HARNESS_SRC.rglob("*.py"))
    )


@pytest.mark.architecture
def test_harness_source_rewrites_no_framework_object() -> None:
    """Replace the patch with a public hook: a middleware, ``request.override(...)``, or a subclass."""
    violations = [
        f"  - {name}:{line} {what}" for name, source in _source_files() for line, what in find_framework_patches(source)
    ]
    assert not violations, "In-place rewrite of a LangChain/LangGraph object:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_harness_source_imports_only_published_framework_names() -> None:
    """Import the name from the module that lists it in ``__all__`` (``langchain.agents.middleware``, not its internals)."""
    violations = [
        f"  - {name}:{line} {what}"
        for name, source in _source_files()
        for line, what in find_non_public_imports(source)
    ]
    assert not violations, "Import of a LangChain/LangGraph name the framework does not publish:\n" + "\n".join(
        violations
    )


@pytest.mark.architecture
def test_documented_modules_without_all_are_all_in_use() -> None:
    """An entry nobody imports from, or one whose module has gained an ``__all__``, no longer belongs on the list."""
    imported = {
        node.module
        for _, source in _source_files()
        for node in ast.walk(_parse(source))
        if isinstance(node, ast.ImportFrom) and node.module in DOCUMENTED_MODULES_WITHOUT_ALL and not node.level
    }
    unused = sorted(DOCUMENTED_MODULES_WITHOUT_ALL - imported)
    published = sorted(module for module in DOCUMENTED_MODULES_WITHOUT_ALL if _published_names(module) is not None)
    assert not unused, f"Not imported from any more, remove from DOCUMENTED_MODULES_WITHOUT_ALL: {unused}"
    assert not published, f"Declares an __all__ now, remove from DOCUMENTED_MODULES_WITHOUT_ALL: {published}"


@pytest.mark.architecture
def test_harness_source_reads_no_private_framework_key_beyond_the_known_ones() -> None:
    """Use the framework's public accessor; a read that has none is listed in ``KNOWN_PRIVATE_KEYS`` with the reason."""
    violations = [
        f"  - {name}:{line} {key!r}"
        for name, source in _source_files()
        for line, key in find_private_framework_keys(source)
        if key not in KNOWN_PRIVATE_KEYS.get(name, frozenset())
    ]
    assert not violations, "Read of a private LangGraph key:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_each_known_private_key_is_still_read() -> None:
    """Once the read is gone the entry is stale and would hide the next one in that file."""
    sources = dict(_source_files())
    stale = sorted(
        f"{name}: {key}"
        for name, keys in KNOWN_PRIVATE_KEYS.items()
        for key in keys
        if key not in {found for _, found in find_private_framework_keys(sources.get(name, ""))}
    )
    assert not stale, f"Remove from KNOWN_PRIVATE_KEYS: {stale}"


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


_FAKE_PUBLISHED: dict[str, frozenset[str] | None] = {
    "langchain.agents.middleware": frozenset({"AgentMiddleware", "ToolCallRequest"}),
    "langchain_core.runnables.config": None,
    "langchain_core._api": frozenset({"beta"}),
}


def _fake_published(module: str) -> frozenset[str] | None:
    if module not in _FAKE_PUBLISHED:
        raise ImportError(module)
    return _FAKE_PUBLISHED[module]


@pytest.mark.architecture
@pytest.mark.parametrize(
    "source",
    [
        "from langchain.agents.middleware import Hidden\n",
        "from langchain.agents.middleware import _helper\n",
        "from langchain_core._api import beta\n",
        "import langchain_core._api\n",
        "from langchain.agents.middleware.types import AgentState\n",
        "from langchain_core.runnables.config import RunnableConfig\n",
        "def late():\n    from langchain.agents.middleware import Hidden\n",
    ],
)
def test_the_import_scanner_sees_each_unpublished_name(source: str) -> None:
    assert find_non_public_imports(source, _fake_published, documented=frozenset())


@pytest.mark.architecture
@pytest.mark.parametrize(
    "source",
    [
        "from langchain.agents.middleware import AgentMiddleware, ToolCallRequest\n",
        "from langchain_core.runnables.config import RunnableConfig\n",
        "import langchain_core.runnables\n",
        "from myrm_agent_harness.agent import _private\n",
        "from . import _sibling\n",
    ],
)
def test_the_import_scanner_accepts_published_names_and_the_harness_own(source: str) -> None:
    documented = frozenset({"langchain_core.runnables.config"})
    assert find_non_public_imports(source, _fake_published, documented) == []


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("source", "keys"),
    [
        ("runtime = config['configurable']['__pregel_runtime']\n", ["__pregel_runtime"]),
        ("config.get('configurable', {}).get('__langgraph_checkpointer')\n", ["__langgraph_checkpointer"]),
        ("KEY = '__pregel_send'\n", ["__pregel_send"]),
        ("key = 'tool_call_id'\nother = '__tool_call_id'\n", []),
        ('"""Reads __pregel_runtime from the config."""\n', []),
    ],
)
def test_the_key_scanner_finds_only_private_framework_keys(source: str, keys: list[str]) -> None:
    assert [key for _, key in find_private_framework_keys(source)] == keys
