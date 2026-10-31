"""Enterprise TLS compatibility for Python 3.13+ / OpenSSL 3.x environments.

Two things go wrong behind a corporate TLS-inspection proxy (Zscaler, Netskope, Palo Alto Prisma, ...):

- Python 3.13 enables ``VERIFY_X509_STRICT``, which enforces RFC 5280 §4.2.1.9 — a CA's ``basicConstraints`` MUST be
  critical. Inspection roots commonly set ``CA:TRUE`` without the critical bit, so the chain is rejected with
  ``BasicConstraints of CA cert not marked critical``.
- The proxy's root lives in the operating system's trust store (pushed by the administrator), not in the CA file
  Python or ``certifi`` ship, so the chain is rejected as an unknown issuer.

When ``MYRM_TLS_STRICT`` is off, ``apply_global_tls_relaxation()`` fixes both at the one place every client gets its
context from: it wraps ``ssl.create_default_context``. A client-purpose context built for the default trust then
validates against the operating system's roots (``truststore``) plus any CA bundle the environment names
(``SSL_CERT_FILE``, ``REQUESTS_CA_BUNDLE``, ``NODE_EXTRA_CA_CERTS``, added on top, never replacing), with only
``VERIFY_X509_STRICT`` cleared. Certificate chain validation, hostname verification and expiry checks stay on, which
is strictly narrower than ``verify=False``. A context built for an explicit CA file, directory or data (a pinned CA)
keeps exactly that trust and only has the strict flag cleared; server-purpose contexts are never touched.

Activation:
    Set ``MYRM_TLS_STRICT=0`` (or ``false``/``no``/``off``). Default (unset) keeps strict verification and installs
    nothing. The host calls ``apply_global_tls_relaxation()`` once at startup, before any client is created.
    Libraries cache the context they were first given (litellm keeps one per CA file for the process), so a change of
    the setting reaches every client only after a restart.

[INPUT]
- ssl (POS: Python standard library SSL module)
- truststore (POS: validates server chains against the operating system's trust store)
- certifi (POS: identifies the default CA bundle httpx asks the standard library for)
- os (POS: environment variable access)

[OUTPUT]
- tls_strict_disabled(): check if strict mode is opted out
- create_httpx_client(): the one construction point of the harness's ``httpx.AsyncClient``
- apply_global_tls_relaxation(): installs the context policy above and relaxes urllib3's context builder; idempotent
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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx
    from _typeshed import ReadableBuffer, StrOrBytesPath

logger = logging.getLogger(__name__)

_TLS_STRICT_ENV = "MYRM_TLS_STRICT"
_TLS_STRICT_OFF_VALUES = frozenset({"0", "false", "no", "off"})

# CA bundles the environment can name; each is added to the trust the context already has.
_EXTRA_CA_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS")

# litellm builds its default context while it is imported and caches one per CA file for the process.
_LITELLM_HTTP_HANDLER = "litellm.llms.custom_httpx.http_handler"

# Set on the wrapped builders so a second install finds the first.
_CONTEXT_POLICY_MARK = "_myrm_enterprise_tls"
_URLLIB3_MARK = "_myrm_strict_relaxed"


def tls_strict_disabled() -> bool:
    """True when ``MYRM_TLS_STRICT`` opts out of OpenSSL strict mode.

    Default (unset / any other value) is strict, matching Python 3.13's own
    default. Only the explicit off-values flip it.
    """
    return os.environ.get(_TLS_STRICT_ENV, "").strip().lower() in _TLS_STRICT_OFF_VALUES


def _clear_x509_strict(ctx: ssl.SSLContext) -> ssl.SSLContext:
    """Clear only ``VERIFY_X509_STRICT`` from a context."""
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag and ctx.verify_flags & strict_flag:
        ctx.verify_flags &= ~strict_flag
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
    stops relaxing every context created afterwards.
    """
    original = ssl.create_default_context
    if getattr(original, _CONTEXT_POLICY_MARK, False):
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

    setattr(create_default_context, _CONTEXT_POLICY_MARK, True)
    ssl.create_default_context = create_default_context


def _discard_litellm_cached_contexts() -> None:
    """Drop the contexts litellm cached before the policy was in place, so the next client it builds gets the policy.

    A context built earlier is strict and trusts only the bundled roots. Contexts a live client already holds are
    not touched. Nothing happens when litellm has not been imported yet: its first context will go through the policy.
    """
    handler = sys.modules.get(_LITELLM_HTTP_HANDLER)
    cache = getattr(handler, "_ssl_context_cache", None)
    if isinstance(cache, dict):
        cache.clear()


def _install_urllib3_relaxation() -> None:
    """Strip ``VERIFY_X509_STRICT`` from urllib3's context builder, which ``requests`` and ``huggingface_hub`` use.

    urllib3 builds its own contexts without going through ``ssl.create_default_context``. A no-op when urllib3
    isn't importable or the patch is already in place.
    """
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    try:
        import urllib3.util.ssl_ as _u3ssl
    except Exception:
        logger.debug("event=tls_urllib3_patch_skipped reason=import_failed")
        return

    _orig = _u3ssl.create_urllib3_context
    if getattr(_orig, _URLLIB3_MARK, False):
        return

    @functools.wraps(_orig)
    def _relaxed_create_urllib3_context(*args: Any, **kwargs: Any) -> ssl.SSLContext:
        ctx = _orig(*args, **kwargs)
        if tls_strict_disabled() and ctx.verify_flags & strict_flag:
            ctx.verify_flags &= ~strict_flag
        return ctx

    setattr(_relaxed_create_urllib3_context, _URLLIB3_MARK, True)
    _u3ssl.create_urllib3_context = _relaxed_create_urllib3_context


def apply_global_tls_relaxation() -> bool:
    """Install the enterprise TLS policy process-wide when ``MYRM_TLS_STRICT`` opts out of strict mode.

    Covers every client that asks the standard library for its context (httpx, litellm's aiohttp transport) and the
    ``urllib3`` chain. Call at application startup before any HTTP client is created; idempotent.

    Returns True when the policy is in place, False when strict mode is on (nothing is installed).
    """
    if not tls_strict_disabled() or not getattr(ssl, "VERIFY_X509_STRICT", 0):
        return False

    _install_default_context_policy()
    _discard_litellm_cached_contexts()
    _install_urllib3_relaxation()
    logger.info("event=tls_enterprise_compat_active")
    return True


def create_httpx_client(**kwargs: Any) -> httpx.AsyncClient:
    """The one construction point of the harness's ``httpx.AsyncClient``.

    The client takes its TLS context from ``ssl.create_default_context``, so the policy
    ``apply_global_tls_relaxation()`` installed applies to it with no per-client injection. A caller-supplied
    ``verify`` is passed through untouched.
    """
    import httpx

    return httpx.AsyncClient(**kwargs)


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
