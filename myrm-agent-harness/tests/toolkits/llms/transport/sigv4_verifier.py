"""Checks an AWS Signature Version 4 header against the request it was computed for, without any AWS library.

[INPUT]
- httpx (POS: the request as it reached the wire)

[OUTPUT]
- Signature: the scope and signed headers one ``Authorization`` header names
- parse_authorization: the fields of an ``AWS4-HMAC-SHA256`` header
- signature_is_valid: whether the header's signature is the one the signing algorithm gives for this request

[POS]
An independent second opinion on the signature the Bedrock wire sends: the verifier rebuilds the canonical request from
the request the server would receive (method, path as sent, the headers the signature names, the body) and signs it
the way the published algorithm says, so a wrong signed-header list, a wrong region or a signature over other bytes
than were sent all fail. It is checked against the signatures the baseline client library sent
(``golden_credentials_baseline.json``), which makes it a verifier of the algorithm, not of one implementation.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import quote

import httpx

_ALGORITHM = "AWS4-HMAC-SHA256"


@dataclass(frozen=True, slots=True)
class Signature:
    """The parts of an ``Authorization`` header that name what was signed."""

    access_key: str
    date: str
    region: str
    service: str
    signed_headers: tuple[str, ...]
    signature: str


def parse_authorization(header: str) -> Signature:
    scheme, _, rest = header.partition(" ")
    if scheme != _ALGORITHM:
        raise ValueError(f"not a Signature Version 4 header: {scheme!r}")
    fields = dict(part.strip().split("=", 1) for part in rest.split(","))
    access_key, date, region, service, _ = fields["Credential"].split("/")
    return Signature(access_key, date, region, service, tuple(fields["SignedHeaders"].split(";")), fields["Signature"])


def _canonical_request(request: httpx.Request, signed_headers: tuple[str, ...]) -> str:
    raw_path, _, query = request.url.raw_path.decode().partition("?")
    headers = "".join(f"{name}:{' '.join(request.headers[name].split())}\n" for name in signed_headers)
    return "\n".join(
        [
            request.method,
            quote(raw_path, safe="/~"),  # a service other than S3 encodes the already encoded path once more
            query,
            headers,
            ";".join(signed_headers),
            hashlib.sha256(request.content).hexdigest(),
        ]
    )


def signature_is_valid(request: httpx.Request, secret_key: str) -> bool:
    signature = parse_authorization(request.headers["authorization"])
    scope = f"{signature.date}/{signature.region}/{signature.service}/aws4_request"
    to_sign = "\n".join(
        [
            _ALGORITHM,
            request.headers["x-amz-date"],
            scope,
            hashlib.sha256(_canonical_request(request, signature.signed_headers).encode()).hexdigest(),
        ]
    )
    key = f"AWS4{secret_key}".encode()
    for part in (signature.date, signature.region, signature.service, "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    return hmac.compare_digest(hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest(), signature.signature)
