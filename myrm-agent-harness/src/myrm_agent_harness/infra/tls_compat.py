"""Enterprise TLS compatibility for Python 3.13+ / OpenSSL 3.x environments.

Two things go wrong behind a corporate TLS-inspection proxy (Zscaler, Netskope, Palo Alto Prisma, ...):

- Python 3.13 enables ``VERIFY_X509_STRICT``, which enforces RFC 5280 §4.2.1.9 — a CA's ``basicConstraints`` MUST be
  critical. Inspection roots commonly set ``CA:TRUE`` without the critical bit, so the chain is rejected with
  ``BasicConstraints of CA cert not marked critical``.
- The proxy's root lives in the operating system's trust store (pushed by the administrator), not in the CA file
  Python or ``certifi`` ship, so the chain is rejected as an unknown issuer.

When ``MYRM_TLS_STRICT`` is off, ``apply_global_tls_relaxation()`` gives every client library the same trust at the
place it takes its context from:

- ``ssl.create_default_context`` is wrapped and ``ssl._create_default_https_context`` (``urllib.request``,
  ``http.client``) points at the wrapper, which reaches httpx, litellm's aiohttp transport and asyncio's ``ssl=True``
  as well. A client-purpose context built for the default trust validates against the operating system's roots
  (``truststore``) plus any CA bundle the environment names (``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``,
  ``NODE_EXTRA_CA_CERTS``, added on top, never replacing), with only ``VERIFY_X509_STRICT`` cleared. A context built
  for an explicit CA file, directory or data (a pinned CA) keeps exactly that trust and only has the strict flag
  cleared; server-purpose contexts are never touched.
- aiohttp builds its default context while it is imported and litellm caches the contexts it builds, so both are
  rebuilt through the wrapper.
- urllib3 (``requests``) builds its contexts without ``ssl.create_default_context``, so its builder gets the same
  trust. A CA file a caller loads into such a context (``verify=path``) is added to that trust, not exclusive.
- A child process inherits none of this. ``with_node_system_ca()`` adds ``NODE_USE_SYSTEM_CA=1`` to the environment of
  a child that may run Node, so it validates against the operating system's store too (Node 22.15+ and 23.8+ read
  it; an older Node ignores it).

Certificate chain validation, hostname verification and expiry checks stay on, which is strictly narrower than
``verify=False``. A client that constructs ``ssl.SSLContext`` itself is outside the policy.

Activation:
    Set ``MYRM_TLS_STRICT=0`` (or ``false``/``no``/``off``). Default (unset) keeps strict verification and installs
    nothing. The host calls ``apply_global_tls_relaxation()`` once at startup, before any client is created.
    Whether to relax is decided when a context is built, but a library that cached a context (litellm keeps one per
    CA file for the process, aiohttp one default) or a client that holds one keeps it, so a change of the setting
    reaches every client only after a restart.

[INPUT]
- ssl (POS: Python standard library SSL module)
- truststore (POS: validates server chains against the operating system's trust store)
- certifi (POS: identifies the default CA bundle httpx asks the standard library for)
- aiohttp, litellm, urllib3 (POS: libraries whose default or cached contexts are brought under the policy when loaded)
- os (POS: environment variable access)
- utils.os_compat::IS_WIN (POS: whether the host operating system is Windows)

[OUTPUT]
- tls_strict_disabled(): check if strict mode is opted out
- with_node_system_ca(): the environment of a child process that may run Node, with the system trust store switched
  on while strict mode is off
- create_httpx_client(): the harness's construction point for ``httpx.AsyncClient``; the policy covers a client
  built directly just the same
- apply_global_tls_relaxation(): installs the context policy above on the standard library, aiohttp, litellm and
  urllib3; idempotent
- is_tls_hard_error(): whether an error text carries a certificate-rejection signal (the single signal list the LLM
  failure classifier and the error diagnostics both read)
- is_tls_transient_error(): whether an error text is an interrupted handshake with no certificate verdict

[POS]
Infrastructure TLS compatibility. Enables enterprise deployments behind
TLS-inspection proxies without disabling certificate verification entirely.
"""

from __future__ import annotations

import functools
import logging
import os
import ssl
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, overload

from myrm_agent_harness.utils.os_compat import IS_WIN

if TYPE_CHECKING:
    import httpx
    from _typeshed import ReadableBuffer, StrOrBytesPath

logger = logging.getLogger(__name__)

_TLS_STRICT_ENV = "MYRM_TLS_STRICT"
_TLS_STRICT_OFF_VALUES = frozenset({"0", "false", "no", "off"})

# CA bundles the environment can name; each is added to the trust the context already has.
_EXTRA_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")

# Makes Node trust the operating system's CA store besides its bundled roots; a Node that does not know it ignores it.
_NODE_SYSTEM_CA_ENV = "NODE_USE_SYSTEM_CA"

# litellm builds its default context while it is imported and caches one per CA file for the process.
_LITELLM_HTTP_HANDLER = "litellm.llms.custom_httpx.http_handler"

# Set on the wrapped builders so a second install finds the first.
_POLICY_MARK = "_myrm_enterprise_tls"

# urllib3 builds ``SSLContext(PROTOCOL_TLS_CLIENT)`` in ``create_urllib3_context`` and several of its modules hold
# their own reference to that function, so the policy is applied by rebinding every one of them.
_URLLIB3_PACKAGE = "urllib3"
_URLLIB3_BUILDER = "create_urllib3_context"
_URLLIB3_CONTEXT_CLASS = "SSLContext"


def tls_strict_disabled() -> bool:
    """True when ``MYRM_TLS_STRICT`` opts out of OpenSSL strict mode.

    Default (unset / any other value) is strict, matching Python 3.13's own
    default. Only the explicit off-values flip it.
    """
    return os.environ.get(_TLS_STRICT_ENV, "").strip().lower() in _TLS_STRICT_OFF_VALUES


@overload
def with_node_system_ca(env: dict[str, str]) -> dict[str, str]: ...
@overload
def with_node_system_ca(env: dict[str, str] | None) -> dict[str, str] | None: ...
def with_node_system_ca(env: dict[str, str] | None) -> dict[str, str] | None:
    """*env* for a child process that may run Node, with ``NODE_USE_SYSTEM_CA=1`` added while strict mode is off.

    A child inherits none of the host's TLS policy and Node validates against its bundled roots, so behind an
    inspection proxy it rejects a chain the host accepts. A value the caller already set wins. While strict mode is
    on, *env* comes back as it is.
    """
    if not tls_strict_disabled():
        return env
    env = {} if env is None else env
    # Windows environment names are case-insensitive, so a differently cased declaration is the caller's own value.
    declared = {key.upper() for key in env} if IS_WIN else set(env)
    if _NODE_SYSTEM_CA_ENV in declared:
        return env
    return {**env, _NODE_SYSTEM_CA_ENV: "1"}


def _clear_x509_strict(ctx: ssl.SSLContext) -> ssl.SSLContext:
    """Clear only ``VERIFY_X509_STRICT`` from a context."""
    if ctx.verify_flags & ssl.VERIFY_X509_STRICT:
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def _platform_trust_context() -> ssl.SSLContext | None:
    """A client context that validates against the operating system's trust store, or None when it cannot be built.

    None sends the caller back to the context the standard library would have built, so a platform where the
    system store is unreachable keeps the narrower trust instead of failing every connection.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception as exc:
        logger.warning("event=tls_platform_trust_unavailable error=%s", exc)
        return None


def _trust_environment_ca_files(ctx: ssl.SSLContext) -> None:
    """Add the CA bundles the environment names to *ctx*; an unreadable bundle is skipped, which only narrows trust."""
    for var in _EXTRA_CA_ENV_VARS:
        path = os.environ.get(var, "").strip()
        if not path or not os.path.isfile(path):
            continue
        try:
            ctx.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError) as exc:
            logger.warning("event=tls_ca_bundle_skipped var=%s error=%s", var, exc)
            continue
        logger.debug("event=tls_ca_bundle_loaded var=%s path=%s", var, path)


def _install_default_context_policy() -> None:
    """Wrap ``ssl.create_default_context`` with the enterprise policy (see the module docstring); idempotent.

    The policy is decided when a context is created, not when the wrapper is installed, so switching the toggle off
    stops relaxing every context created afterwards. ``ssl._create_default_https_context``, which ``urllib.request``
    and ``http.client`` call, is the standard builder bound when ``ssl`` was imported and is pointed at the wrapper
    unless the host already replaced it.
    """
    original = ssl.create_default_context
    if getattr(original, _POLICY_MARK, False):
        return

    import certifi

    bundled_cafile = certifi.where()

    @functools.wraps(original)
    def create_default_context(
        purpose: ssl.Purpose = ssl.Purpose.SERVER_AUTH,
        *,
        cafile: StrOrBytesPath | None = None,
        capath: StrOrBytesPath | None = None,
        cadata: str | ReadableBuffer | None = None,
    ) -> ssl.SSLContext:
        if purpose is not ssl.Purpose.SERVER_AUTH or not tls_strict_disabled():
            return original(purpose, cafile=cafile, capath=capath, cadata=cadata)
        if capath is None and cadata is None and cafile in (None, bundled_cafile):
            ctx = _platform_trust_context() or original(purpose, cafile=cafile)
            _trust_environment_ca_files(ctx)
        else:
            ctx = original(purpose, cafile=cafile, capath=capath, cadata=cadata)
        return _clear_x509_strict(ctx)

    setattr(create_default_context, _POLICY_MARK, True)
    if ssl._create_default_https_context is original:
        ssl._create_default_https_context = create_default_context
    ssl.create_default_context = create_default_context


def _rebuild_aiohttp_default_context() -> None:
    """Replace the verified context aiohttp built while it was imported, so a session that names no context gets the policy.

    aiohttp builds it once, at import time, to keep disk I/O off the event loop, and litellm imports aiohttp before a
    host reads the setting. The context is rebuilt with aiohttp's own builder, which asks ``ssl.create_default_context``.
    Nothing happens when aiohttp has not been imported yet: its first context will go through the policy.
    """
    if "aiohttp.connector" not in sys.modules:
        return
    from aiohttp import connector

    build = getattr(connector, "_make_ssl_context", None)
    if not callable(build) or not hasattr(connector, "_SSL_CONTEXT_VERIFIED"):
        logger.warning("event=tls_aiohttp_default_context_unavailable")
        return
    connector._SSL_CONTEXT_VERIFIED = build(True)


def _discard_litellm_cached_contexts() -> None:
    """Drop the contexts litellm cached before the policy was in place, so the next client it builds gets the policy.

    A context built earlier is strict and trusts only the bundled roots. Contexts a live client already holds are
    not touched. Nothing happens when litellm has not been imported yet: its first context will go through the policy.
    """
    handler = sys.modules.get(_LITELLM_HTTP_HANDLER)
    cache = getattr(handler, "_ssl_context_cache", None)
    if isinstance(cache, dict):
        cache.clear()


def _with_enterprise_trust[**P](build: Callable[P, ssl.SSLContext]) -> Callable[P, ssl.SSLContext]:
    """*build* with the environment's CA bundles added and ``VERIFY_X509_STRICT`` cleared while strict mode is off."""

    @functools.wraps(build)
    def build_with_enterprise_trust(*args: P.args, **kwargs: P.kwargs) -> ssl.SSLContext:
        ctx = build(*args, **kwargs)
        if tls_strict_disabled():
            _trust_environment_ca_files(ctx)
            _clear_x509_strict(ctx)
        return ctx

    setattr(build_with_enterprise_trust, _POLICY_MARK, True)
    return build_with_enterprise_trust


def _install_urllib3_policy() -> None:
    """Give urllib3's context builder, which ``requests`` uses, the trust ``ssl.create_default_context`` now gives.

    urllib3 builds ``SSLContext(PROTOCOL_TLS_CLIENT)`` in ``create_urllib3_context`` without asking the standard
    library, so the class it instantiates becomes a factory that returns the system-store context while strict mode is
    off, and the builder adds the environment's CA bundles and clears the strict flag. A no-op when urllib3 is not
    importable or the policy is already in place.
    """
    try:
        import urllib3.util.ssl_ as urllib3_ssl
    except ImportError:
        logger.debug("event=tls_urllib3_policy_skipped reason=import_failed")
        return

    builder = getattr(urllib3_ssl, _URLLIB3_BUILDER)
    if getattr(builder, _POLICY_MARK, False):
        return

    standard_class: Callable[[int], ssl.SSLContext] = getattr(urllib3_ssl, _URLLIB3_CONTEXT_CLASS)

    def create_context(protocol: int) -> ssl.SSLContext:
        if protocol == ssl.PROTOCOL_TLS_CLIENT and tls_strict_disabled():
            return _platform_trust_context() or standard_class(protocol)
        return standard_class(protocol)

    setattr(urllib3_ssl, _URLLIB3_CONTEXT_CLASS, create_context)
    governed = _with_enterprise_trust(builder)
    for name, module in list(sys.modules.items()):
        if (name == _URLLIB3_PACKAGE or name.startswith(f"{_URLLIB3_PACKAGE}.")) and (
            getattr(module, _URLLIB3_BUILDER, None) is builder
        ):
            setattr(module, _URLLIB3_BUILDER, governed)


def apply_global_tls_relaxation() -> bool:
    """Install the enterprise TLS policy process-wide when ``MYRM_TLS_STRICT`` opts out of strict mode.

    Covers the standard library's builders (httpx, ``urllib.request``, ``http.client``, asyncio), aiohttp's default
    context, litellm's cached contexts and urllib3's builder (``requests``). Call at application startup before any
    HTTP client is created; idempotent.

    Returns True when the policy is in place, False when strict mode is on (nothing is installed).
    """
    if not tls_strict_disabled():
        return False

    _install_default_context_policy()
    _rebuild_aiohttp_default_context()
    _discard_litellm_cached_contexts()
    _install_urllib3_policy()
    logger.info("event=tls_enterprise_compat_active")
    return True


def create_httpx_client(**kwargs: object) -> httpx.AsyncClient:
    """Construct the harness's ``httpx.AsyncClient``.

    The client takes its TLS context from ``ssl.create_default_context``, so the policy
    ``apply_global_tls_relaxation()`` installed covers every ``httpx`` client in the process, this one and a directly
    constructed one alike. Every keyword argument, a caller-supplied ``verify`` included, reaches
    ``httpx.AsyncClient`` untouched and is validated there.
    """
    import httpx

    return httpx.AsyncClient(**kwargs)  # type: ignore[arg-type]


# Hard TLS failure signals: the certificate/chain itself is rejected.
# These are permanent (fail-fast) — retrying cannot change the verdict.
# Python/OpenSSL strict-mode wordings come first, then the Bun/Node ones
# (e.g. "unable to verify the first certificate"), hostname/altname mismatch
# and an expired leaf — all deliberately hard. A wording that differs from
# another only in a separator or an apostrophe (the "self_signed" of Node's
# DEPTH_ZERO_SELF_SIGNED_CERT, a typographic apostrophe) is listed as its own signal.
_TLS_HARD_SIGNALS = (
    "basic constraints",
    "basicconstraints",
    "basic_constraints",
    "basic-constraints",
    "not marked critical",
    "certificate verify failed",
    "ssl: certificate_verify_failed",
    "unable to get local issuer",
    "[ssl: certificate_verify_failed]",
    "self-signed certificate in certificate chain",
    "self-signed",
    "self signed",
    "self_signed",
    "selfsigned",
    "unable to verify the first certificate",
    "hostname mismatch",
    "hostname doesn't match",
    "hostname doesn\u2019t match",
    "hostname doesnt match",
    "certificate has expired",
    "cert has expired",
    "certificate expired",
    "expired certificate",
    "err_tls_cert_altname_invalid",
    "altname",
)

# Transient TLS transport signals: the handshake was interrupted before any
# certificate verdict (weak network, proxy reset, Bun mislabel). Bun's
# "unknown certificate verification error" belongs here: it is emitted when
# the connection is reset mid-handshake, with no certificate ever rejected.
_TLS_TRANSIENT_PATTERNS = (
    "unknown certificate verification",
    "unknown_certificate_verification",
    "certificate verification error",
    "ssl routines",
    "handshake failure",
    "failure in handshake",
    "unexpected eof",
    "eof occurred in violation of protocol",
    "broken pipe",
    "wrong version number",
    "bad record mac",
    "decryption failed",
    "tlsv1 alert",
    "ssl3_read_bytes",
    "ssl3_write_bytes",
)


def is_tls_hard_error(error_message: str) -> bool:
    """Detect a permanent TLS failure (bad chain, not a flaky network).

    Covers the strict-mode, Bun, Node and OpenSSL wordings of a rejected certificate.
    Hard failures must fail fast with remediation — never retried.
    """
    lower = error_message.lower()
    return any(pattern in lower for pattern in _TLS_HARD_SIGNALS)


def is_tls_transient_error(error_message: str) -> bool:
    """Detect an interrupted TLS handshake with no certificate verdict.

    True when transport-level signals are present and no hard signal matches.
    Callers should treat this as retryable (same class as connection reset).
    """
    lower = error_message.lower()
    if any(pattern in lower for pattern in _TLS_HARD_SIGNALS):
        return False
    return any(pattern in lower for pattern in _TLS_TRANSIENT_PATTERNS)
