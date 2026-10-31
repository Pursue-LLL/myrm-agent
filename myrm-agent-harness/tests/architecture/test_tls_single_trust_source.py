"""Every TLS context the harness builds goes through the enterprise network compatibility policy, except in the module that implements it.

[INPUT]
- src/myrm_agent_harness/**/*.py: every ``SSLContext(...)`` and ``_create_unverified_context(...)`` call

[OUTPUT]
- Fails when a module other than ``infra/tls_compat.py`` builds a TLS context by hand: such a context ignores
  ``MYRM_TLS_STRICT`` and the operating system trust store, and no test of the policy would notice it.

[POS]
tests/architecture/test_tls_single_trust_source.py - guard for ``infra/tls_compat.py``: ``ssl.create_default_context``
and the HTTP clients follow the policy; only a context built directly escapes it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness"
_POLICY_MODULE = "infra/tls_compat.py"
_DIRECT_BUILDERS = frozenset({"SSLContext", "_create_unverified_context"})


def direct_context_builds(source: str) -> Iterator[tuple[int, str]]:
    """``(line, builder)`` for each call in *source* that builds a TLS context without ``ssl.create_default_context``."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name in _DIRECT_BUILDERS:
            yield node.lineno, name


@pytest.mark.architecture
def test_only_the_policy_module_builds_a_tls_context_by_hand() -> None:
    offenders = [
        f"{relative}:{line}: {builder}(...)"
        for path in sorted(_SRC.rglob("*.py"))
        if (relative := path.relative_to(_SRC).as_posix()) != _POLICY_MODULE
        for line, builder in direct_context_builds(path.read_text(encoding="utf-8"))
    ]

    assert not offenders, (
        "build the context with ssl.create_default_context or myrm_agent_harness.infra.tls_compat.create_httpx_client "
        "so it follows the enterprise network compatibility setting:\n" + "\n".join(offenders)
    )


@pytest.mark.architecture
def test_the_policy_module_still_builds_a_context() -> None:
    assert list(direct_context_builds((_SRC / _POLICY_MODULE).read_text(encoding="utf-8")))


class TestTheScannerSeesWhatItShould:
    def test_a_context_built_through_the_ssl_module_is_found(self) -> None:
        source = "ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)"

        assert list(direct_context_builds(source)) == [(1, "SSLContext")]

    def test_a_context_built_through_a_from_import_is_found(self) -> None:
        source = "from ssl import SSLContext\nctx = SSLContext(ssl.PROTOCOL_TLS_CLIENT)"

        assert list(direct_context_builds(source)) == [(2, "SSLContext")]

    def test_the_unverified_builder_is_found(self) -> None:
        assert list(direct_context_builds("ctx = ssl._create_unverified_context()")) == [
            (1, "_create_unverified_context")
        ]

    def test_the_policy_aware_builders_a_type_check_and_an_annotation_are_not_builds(self) -> None:
        source = (
            "ctx = ssl.create_default_context(cafile=path)\n"
            "ok = isinstance(ctx, ssl.SSLContext)\n"
            "def use(context: ssl.SSLContext) -> None: ...\n"
        )

        assert list(direct_context_builds(source)) == []
