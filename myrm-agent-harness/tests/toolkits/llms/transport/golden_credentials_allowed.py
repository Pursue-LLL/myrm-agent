"""Registry of the credential facts the installed stack sends differently from the baseline, each with its reason.

[INPUT]
- golden_compare::Allowed (POS: one entry: the facts that changed, with their new values, and why they are right)

[OUTPUT]
- CREDENTIAL_ALLOWED: the recorded cases whose credential facts changed

[POS]
A credential is read once into the headers a provider authenticates with, so an entry exists only where the new request
is the one the provider should receive; the reason says why. ``test_golden_credentials`` fails on a changed fact with no
entry, on an entry whose facts differ from what happens now, and on an entry whose case no longer differs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .golden_compare import Allowed

_BEARER_BESIDE_KEY: Final = (
    "A bearer Authorization header carrying the same key was added next to the vendor's own key header (x-api-key, "
    "api-key); the vendor reads the key header alone, and only gateways in front of Anthropic expect the bearer."
)
_FETCHED_BETA_LIST: Final = (
    "Before the call, the baseline library downloaded a beta-header configuration file from raw.githubusercontent.com, "
    "so a chat call depended on a third-party host; the transport contacts no host but the provider's."
)
_DOUBLED_AUTHORIZATION: Final = (
    "A subscription (OAuth) token was sent in two identical Authorization headers; one is sent."
)
_BODY_LEAK: Final = (
    "The caller's `model_kwargs` container, the Entra token inside it included, was copied into the request body as an "
    "unknown top-level field; the token travels only in the Authorization header."
)

CREDENTIAL_ALLOWED: Final[Mapping[str, Allowed]] = {
    **{
        case: Allowed({"h.authorization": None}, _BEARER_BESIDE_KEY)
        for case in (
            "anthropic|key_official",
            "anthropic|key_structured",
            "azure_responses|default",
            "azure_responses|version_env",
            "azure_responses|version_explicit",
            "azure|key_explicit",
            "azure|stream",
            "azure|version_env",
            "azure|version_explicit",
            "azure|version_explicit_over_env",
        )
    },
    "anthropic|key_caller_beta": Allowed(
        {"h.authorization": None, "other_requests": []}, f"{_BEARER_BESIDE_KEY} {_FETCHED_BETA_LIST}"
    ),
    **{
        case: Allowed({"h.authorization": "Bearer <oauth_token>"}, _DOUBLED_AUTHORIZATION)
        for case in (
            "anthropic|oauth_caller_beta",
            "anthropic|oauth_gateway",
            "anthropic|oauth_official",
            "anthropic|oauth_stream",
            "anthropic|oauth_structured",
        )
    },
    "azure|ad_token": Allowed({"secrets_in_body": []}, _BODY_LEAK),
    "azure|ad_token_and_key": Allowed(
        {"h.authorization": "Bearer <ad_token>", "secrets_in_body": []},
        f"{_BODY_LEAK} With both a resource key and an Entra token, the baseline library sent the resource key as the "
        "bearer token and not the Entra token; the token is the credential and the key is not sent.",
    ),
    "bedrock|bearer_env": Allowed(
        {
            "h.authorization": "Bearer <env_key>",
            "query": "",
            "raised": False,
            "requests": 1,
            "secrets_in_body": [],
            "secrets_in_url": [],
            "url": "https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-3-5-sonnet-20241022-v2%3A0/converse",
        },
        "The Bedrock profile's key variable AWS_BEARER_TOKEN_BEDROCK supplies the bearer token; the baseline library never "
        "read it and failed with 'Unable to locate credentials'.",
    ),
}
