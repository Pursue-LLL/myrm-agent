"""Drift guard for ``MemoryManagerHost``, the annotation-only base of the manager parts.

The host declares, for static checkers only, the attributes the core assigns and the methods
the mixins call on each other. Nothing at runtime enforces that these declarations still
describe the real manager, so these tests compare them with it:

- every stub names a member ``MemoryManager`` really defines, with the same member kind
  (method, property, staticmethod), async-ness and parameter names, kinds and defaults;
- every declared attribute is a slot of ``MemoryManagerCore``, the class that assigns it;
- the host carries no runtime members, so a stub can never stand in for a missing implementation.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory._manager import MemoryManager, host
from myrm_agent_harness.toolkits.memory._manager.core import MemoryManagerCore

_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
_NO_DEFAULT = object()
# (name, kind, default): ``default`` is ``_NO_DEFAULT`` when the parameter is required.
_Param = tuple[str, inspect._ParameterKind, object]

_HOST_CLASS = next(
    node for node in ast.parse(Path(host.__file__).read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef)
)
_STUBS: dict[str, _FunctionNode] = {
    node.name: node
    for statement in _HOST_CLASS.body
    if isinstance(statement, ast.If)
    for node in statement.body
    if isinstance(node, _FunctionNode)
}
_DECLARED_ATTRIBUTES = [
    statement.target.id
    for statement in _HOST_CLASS.body
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
]


def _literal(node: ast.expr | None) -> object:
    """The literal default of a stub parameter, ``_NO_DEFAULT`` when absent, the source text otherwise."""
    if node is None:
        return _NO_DEFAULT
    try:
        return ast.literal_eval(node)
    except ValueError:
        return ast.unparse(node)


def _stub_params(stub: _FunctionNode) -> list[_Param]:
    arguments = stub.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = [None] * (len(positional) - len(arguments.defaults)) + list(arguments.defaults)
    params: list[_Param] = []
    for index, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        kind = (
            inspect.Parameter.POSITIONAL_ONLY
            if index < len(arguments.posonlyargs)
            else inspect.Parameter.POSITIONAL_OR_KEYWORD
        )
        params.append((arg.arg, kind, _literal(default)))
    if arguments.vararg:
        params.append((arguments.vararg.arg, inspect.Parameter.VAR_POSITIONAL, _NO_DEFAULT))
    params.extend(
        (arg.arg, inspect.Parameter.KEYWORD_ONLY, _literal(default))
        for arg, default in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
    )
    if arguments.kwarg:
        params.append((arguments.kwarg.arg, inspect.Parameter.VAR_KEYWORD, _NO_DEFAULT))
    return params


def _real_params(function: Callable[..., object]) -> list[_Param]:
    return [
        (
            parameter.name,
            parameter.kind,
            _NO_DEFAULT if parameter.default is inspect.Parameter.empty else parameter.default,
        )
        for parameter in inspect.signature(function).parameters.values()
    ]


def _stub_kind(stub: _FunctionNode) -> str:
    decorators = {ast.unparse(decorator) for decorator in stub.decorator_list}
    if "property" in decorators:
        return "property"
    return "staticmethod" if "staticmethod" in decorators else "method"


def _implementation(name: str) -> tuple[str, Callable[..., object]]:
    """The member kind and underlying function ``MemoryManager`` defines for ``name``."""
    member = inspect.getattr_static(MemoryManager, name)
    if isinstance(member, property):
        assert member.fget is not None
        return "property", member.fget
    if isinstance(member, staticmethod):
        return "staticmethod", member.__func__
    assert inspect.isfunction(member), f"{name} is not a method of MemoryManager"
    return "method", member


def test_host_declares_stubs_and_attributes() -> None:
    assert _STUBS, "no method stubs found under TYPE_CHECKING in MemoryManagerHost"
    assert _DECLARED_ATTRIBUTES, "no attribute annotations found on MemoryManagerHost"


@pytest.mark.parametrize("name", sorted(_STUBS))
def test_stub_matches_implementation(name: str) -> None:
    stub = _STUBS[name]
    kind, function = _implementation(name)

    assert _stub_kind(stub) == kind, f"{name}: stub is a {_stub_kind(stub)}, implementation is a {kind}"
    assert isinstance(stub, ast.AsyncFunctionDef) == inspect.iscoroutinefunction(function), (
        f"{name}: async-ness differs from the implementation"
    )

    expected = _real_params(function)
    actual = _stub_params(stub)
    assert [(n, k) for n, k, _ in actual] == [(n, k) for n, k, _ in expected], (
        f"{name}: parameter names or kinds differ from the implementation"
    )
    for (param, _, stub_default), (_, _, real_default) in zip(actual, expected, strict=True):
        if stub_default is _NO_DEFAULT or real_default is _NO_DEFAULT:
            assert stub_default is real_default, f"{name}.{param}: default presence differs"
        elif not isinstance(stub_default, str):
            assert stub_default == real_default, f"{name}.{param}: default differs"


@pytest.mark.parametrize("name", _DECLARED_ATTRIBUTES)
def test_declared_attribute_is_a_core_slot(name: str) -> None:
    assert name in MemoryManagerCore.__slots__


def test_host_has_no_runtime_members() -> None:
    assert host.MemoryManagerHost.__slots__ == ()
    runtime_members = [
        member
        for member, value in vars(host.MemoryManagerHost).items()
        if not member.startswith("__") and (callable(value) or isinstance(value, property))
    ]
    assert runtime_members == []
