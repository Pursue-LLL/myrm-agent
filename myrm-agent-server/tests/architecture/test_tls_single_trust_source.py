"""Every TLS connection the server, and every prebuilt skill script, opens verifies the peer.

[INPUT]
- app/**/*.py and assets/**/*.py: every ``SSLContext(...)`` and ``_create_unverified_context(...)`` call, and every call
  of a stdlib TLS client (``smtplib.SMTP_SSL``, ``imaplib.IMAP4_SSL``, ``poplib.POP3_SSL``, ``ftplib.FTP_TLS``,
  ``.starttls``)

[OUTPUT]
- Fails when a module builds a TLS context by hand (it ignores ``MYRM_TLS_STRICT`` and the operating system trust
  store), or opens a stdlib TLS connection that passes no context keyword (the stdlib falls back to
  ``ssl._create_stdlib_context``, an unverified context, so the peer is not checked at all). It matches calls by name,
  so a builder renamed on import (``from ssl import SSLContext as Ctx``), bound to a variable first or reached through
  ``getattr`` is not seen, and a client that turns verification off (``verify=False``) is not a context build. Either
  keyword name (``context``, ``ssl_context``) satisfies the check for any client; the name a client really accepts is
  pinned by the tests of its call site, where a wrong one is a ``TypeError``.

[POS]
tests/architecture/test_tls_single_trust_source.py - server half of the guard for ``myrm_agent_harness.infra.tls_compat``.
The policy takes effect where a client takes its context from ``ssl.create_default_context`` (httpx, urllib, asyncio) or
from the urllib3 and aiohttp context builders; this guard covers the two ways around it that live in server code. A
prebuilt skill script runs in a child process the policy never reaches: it takes its trust from
``ssl.create_default_context`` too, which honours ``SSL_CERT_FILE``. The S3 backup client reaches its own TLS stack and
is pinned by ``test_remote_s3_tls.py``.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
# ``assets/`` holds the prebuilt skill scripts, which open their own connections.
_SCANNED_ROOTS = (_SERVER_ROOT / "app", _SERVER_ROOT / "assets")
_DIRECT_BUILDERS = frozenset({"SSLContext", "_create_unverified_context"})
# Stdlib clients whose default, when no context is passed, is ``ssl._create_stdlib_context()``: an unverified one.
_STDLIB_TLS_CLIENTS = frozenset({"SMTP_SSL", "IMAP4_SSL", "POP3_SSL", "FTP_TLS", "starttls"})
_CONTEXT_KEYWORDS = frozenset({"context", "ssl_context"})


def _calls(source: str) -> Iterator[tuple[ast.Call, str]]:
    """Each call in *source* whose callee is a plain or attribute name, with that name."""
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        if name:
            yield node, name


def direct_context_builds(source: str) -> Iterator[tuple[int, str]]:
    """``(line, builder)`` for each call in *source* that builds a TLS context without ``ssl.create_default_context``."""
    for node, name in _calls(source):
        if name in _DIRECT_BUILDERS:
            yield node.lineno, name


def stdlib_clients_without_context(source: str) -> Iterator[tuple[int, str]]:
    """``(line, client)`` for each stdlib TLS client call in *source* that passes no context, or ``context=None``."""
    for node, name in _calls(source):
        if name not in _STDLIB_TLS_CLIENTS:
            continue
        passed = any(
            keyword.arg in _CONTEXT_KEYWORDS and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
            for keyword in node.keywords
        )
        if not passed:
            yield node.lineno, name


def _sources() -> Iterator[tuple[str, str]]:
    """``(path relative to the server root, source)`` of each Python file under the scanned roots."""
    for root in _SCANNED_ROOTS:
        for path in sorted(root.rglob("*.py")):
            yield path.relative_to(_SERVER_ROOT).as_posix(), path.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_every_scanned_root_holds_python_sources() -> None:
    """A root that no longer exists (moved, renamed) would make both scans below pass over nothing."""
    empty = [root.name for root in _SCANNED_ROOTS if not any(root.rglob("*.py"))]

    assert not empty, f"no Python sources under: {', '.join(empty)}"


@pytest.mark.architecture
def test_no_module_builds_a_tls_context_by_hand() -> None:
    offenders = [
        f"{name}:{line}: {builder}(...)" for name, source in _sources() for line, builder in direct_context_builds(source)
    ]

    assert not offenders, (
        "build the context with ssl.create_default_context (in server code also "
        "myrm_agent_harness.infra.tls_compat.create_httpx_client) so it follows the trust settings:\n" + "\n".join(offenders)
    )


@pytest.mark.architecture
def test_no_module_opens_a_stdlib_tls_connection_without_a_context() -> None:
    offenders = [
        f"{name}:{line}: {client}(...)" for name, source in _sources() for line, client in stdlib_clients_without_context(source)
    ]

    assert not offenders, (
        "pass ssl.create_default_context() as the context (ssl_context= for imaplib): without one the stdlib client "
        "does not verify the server certificate:\n" + "\n".join(offenders)
    )


class TestTheScannerSeesWhatItShould:
    def test_a_context_built_through_the_ssl_module_is_found(self) -> None:
        source = "ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)"

        assert list(direct_context_builds(source)) == [(1, "SSLContext")]

    def test_a_context_built_through_a_from_import_is_found(self) -> None:
        source = "from ssl import SSLContext\nctx = SSLContext(ssl.PROTOCOL_TLS_CLIENT)"

        assert list(direct_context_builds(source)) == [(2, "SSLContext")]

    def test_the_unverified_builder_is_found(self) -> None:
        assert list(direct_context_builds("ctx = ssl._create_unverified_context()")) == [(1, "_create_unverified_context")]

    def test_the_policy_aware_builders_a_type_check_and_an_annotation_are_not_builds(self) -> None:
        source = (
            "ctx = ssl.create_default_context(cafile=path)\n"
            "ok = isinstance(ctx, ssl.SSLContext)\n"
            "def use(context: ssl.SSLContext) -> None: ...\n"
        )

        assert list(direct_context_builds(source)) == []

    def test_a_stdlib_tls_client_without_a_context_is_found(self) -> None:
        source = (
            "conn = imaplib.IMAP4_SSL(host, port)\n"
            "server = smtplib.SMTP_SSL(host, port, timeout=30)\n"
            "server.starttls()\n"
            "pop = poplib.POP3_SSL(host)\n"
            "ftp = ftplib.FTP_TLS(host)\n"
        )

        assert list(stdlib_clients_without_context(source)) == [
            (1, "IMAP4_SSL"),
            (2, "SMTP_SSL"),
            (3, "starttls"),
            (4, "POP3_SSL"),
            (5, "FTP_TLS"),
        ]

    def test_a_stdlib_tls_client_given_a_context_is_not_found(self) -> None:
        source = (
            "conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())\n"
            "server = smtplib.SMTP_SSL(host, port, timeout=30, context=ctx)\n"
            "server.starttls(context=ctx)\n"
        )

        assert list(stdlib_clients_without_context(source)) == []

    def test_a_context_of_none_is_not_a_context(self) -> None:
        assert list(stdlib_clients_without_context("server.starttls(context=None)")) == [(1, "starttls")]

    def test_either_keyword_name_satisfies_any_client(self) -> None:
        """The scan does not know which name a client takes; the tests of the call site pin that."""
        source = "conn = imaplib.IMAP4_SSL(host, context=ctx)\nserver = smtplib.SMTP_SSL(host, ssl_context=ctx)\n"

        assert list(stdlib_clients_without_context(source)) == []
