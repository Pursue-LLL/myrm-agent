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
snapshot, and signing itself does no I/O. The chain is resolved once for as long as the variables that choose its
source (key pair, session token, profile) stay the same, and botocore refreshes the credentials that expire. The
signature covers the bytes of the attempt being sent, which is why it is made by a hook of the HTTP layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
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


@lru_cache(maxsize=4)
def _session(chain_env: tuple[str | None, ...]) -> Session:
    """One session per source of credentials; the argument is the cache key, botocore reads the variables itself."""
    from botocore.session import Session

    return Session()


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
