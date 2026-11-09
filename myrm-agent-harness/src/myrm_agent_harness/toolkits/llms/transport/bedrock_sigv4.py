"""AWS Signature Version 4 for the Bedrock wire: the credential chain and the signature of one request.

[INPUT]
- botocore (POS: the AWS credential chain and the Signature Version 4 signer; imported only when a request is signed,
  so a deployment that authenticates with a Bedrock API key never loads it)
- transport.http (POS: RequestSigner, the hook that signs each attempt)
- transport.profile (POS: UnsupportedProviderError)

[OUTPUT]
- AwsCredentials / FrozenCredentials: what one request is signed with, and the region the active profile names
- load_credentials: resolve the AWS credential chain (blocking: files, instance metadata, a token service)
- request_signer: the ``RequestSigner`` that signs a request for one region

[POS]
Bedrock accepts a Bedrock API key as a bearer token, and otherwise wants every request signed with AWS credentials
from the standard chain (environment variables, shared credentials file, SSO, web identity, container or instance
role). ``load_credentials`` may block on disk and network, so the facade runs it off the event loop; it returns a
snapshot, and signing itself does no I/O. A session is kept for as long as the variables that choose its source (key
pair, session token, profile) stay the same. Credentials botocore renews itself (SSO, roles, instance metadata, a
helper process that reports an expiry) are never resolved again; the ones it cannot renew (a key pair in a file or the
environment, a token without an expiry) are read again every five minutes, because a login tool may have rewritten
them. The signature covers the bytes of the attempt being sent, which is why it is made by a hook of the HTTP layer.
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

import httpx

from myrm_agent_harness.toolkits.llms.transport.http import RequestSigner
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError

if TYPE_CHECKING:
    from botocore.session import Session

_SERVICE: Final = "bedrock"
# The variables that choose which source of the chain answers (and which files it reads); a change in any of them
# resolves the chain afresh.
_CHAIN_ENV: Final = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_CONFIG_FILE",
    "AWS_ROLE_ARN",
    "AWS_WEB_IDENTITY_TOKEN_FILE",
)
# A session whose credentials botocore cannot renew is replaced after this long: their sources are files and variables
# that a login tool may rewrite while the process runs. At most ``_MAX_SESSIONS`` sessions are kept.
_STATIC_CREDENTIALS_TTL_SECONDS: Final = 300.0
_MAX_SESSIONS: Final = 4
# Headers in the signature: the ones AWS requires and every ``x-amz-*`` / ``x-amzn-*`` the caller adds. The others
# (``Accept-Encoding``, ``Content-Length``, ``Connection``, ...) may be rewritten on the way, so they stay out.
_SIGNED_NAMES: Final = frozenset({"host", "content-type", "date"})
_SIGNED_PREFIXES: Final = ("x-amz-", "x-amzn-")
_SIGNATURE_HEADERS: Final = ("Authorization", "X-Amz-Date", "X-Amz-Security-Token")
_NEEDS_BOTOCORE: Final = (
    "Signing Bedrock requests with AWS credentials needs the botocore package (pip install botocore); "
    "a Bedrock API key (api_key or AWS_BEARER_TOKEN_BEDROCK) needs nothing extra"
)
_NO_CREDENTIALS: Final = (
    "No Bedrock credentials found: set a Bedrock API key (api_key or AWS_BEARER_TOKEN_BEDROCK) or configure AWS "
    "credentials (environment variables, shared credentials file, SSO or an IAM role)"
)


class FrozenCredentials(Protocol):
    """The three values a signature needs; botocore's ``ReadOnlyCredentials`` is one."""

    @property
    def access_key(self) -> str: ...

    @property
    def secret_key(self) -> str: ...

    @property
    def token(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class AwsCredentials:
    """What one request is signed with, frozen so signing needs no further lookup."""

    frozen: FrozenCredentials
    region: str | None


@dataclass(slots=True)
class _CachedSession:
    session: Session
    created_at: float


_sessions: OrderedDict[tuple[str | None, ...], _CachedSession] = OrderedDict()
_sessions_lock = threading.Lock()


def _session(chain_env: tuple[str | None, ...]) -> Session:
    """The session of one source of credentials; ``chain_env`` is the cache key, botocore reads the variables itself.

    A session whose credentials botocore renews keeps them for good. Any other is replaced once it is older than
    ``_STATIC_CREDENTIALS_TTL_SECONDS``, so that a rewritten file or helper output is read again. The chain itself is
    resolved by the first ``get_credentials`` call, which the caller makes outside the lock.
    """
    from botocore.credentials import RefreshableCredentials
    from botocore.session import Session

    with _sessions_lock:
        now = time.monotonic()
        cached = _sessions.get(chain_env)
        if cached is None or (
            now - cached.created_at >= _STATIC_CREDENTIALS_TTL_SECONDS
            and not isinstance(cached.session.get_credentials(), RefreshableCredentials)
        ):
            cached = _sessions[chain_env] = _CachedSession(Session(), now)
        _sessions.move_to_end(chain_env)
        while len(_sessions) > _MAX_SESSIONS:
            _sessions.popitem(last=False)
        return cached.session


def load_credentials() -> AwsCredentials:
    """The credentials of the AWS chain; ``UnsupportedProviderError`` when botocore or the credentials are missing."""
    try:
        from botocore.exceptions import BotoCoreError
    except ImportError as exc:
        raise UnsupportedProviderError(_NEEDS_BOTOCORE) from exc
    try:
        session = _session(tuple(os.environ.get(name) for name in _CHAIN_ENV))
        credentials = session.get_credentials()
        if credentials is None:
            raise UnsupportedProviderError(_NO_CREDENTIALS)
        return AwsCredentials(credentials.get_frozen_credentials(), session.get_config_variable("region"))
    except BotoCoreError as exc:
        raise UnsupportedProviderError(f"AWS credentials could not be loaded: {exc}") from exc


def _is_signed(name: str) -> bool:
    lowered = name.lower()
    return lowered in _SIGNED_NAMES or lowered.startswith(_SIGNED_PREFIXES)


def request_signer(credentials: AwsCredentials, region: str) -> RequestSigner:
    """The hook that adds the signature of the request it is handed; it does no I/O and keeps no state."""
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    auth = SigV4Auth(credentials.frozen, _SERVICE, region)

    def sign(request: httpx.Request) -> None:
        signed = {name: value for name, value in request.headers.items() if _is_signed(name)}
        prepared = AWSRequest(method=request.method, url=str(request.url), data=request.content, headers=signed)
        auth.add_auth(prepared)
        for name in _SIGNATURE_HEADERS:
            if name in prepared.headers:
                request.headers[name] = prepared.headers[name]

    return sign
