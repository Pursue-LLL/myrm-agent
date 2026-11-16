"""What the egress guard lets a browser connect to: the SSRF policy applied to one connection.

[INPUT]
- core.security.http.secure_fetch::parse_allowed_internal_hosts (POS: the operator's exact-host exemptions, honored by every fetch tier)
- utils.url_utils::is_blocked_ip, validate_scheme_and_hostname (POS: the IP blocklist and hostname rules every SSRF check shares)

[OUTPUT]
- Resolver: the guard's policy hook, ``(host, port) -> addresses to dial``
- EgressRefusedError: a resolver's verdict that a destination must not be dialed
- resolve_public_addresses: the default resolver, the cloud policy of the fetch tiers
- environment_proxy_configured: whether the environment sends the process's HTTP traffic through a proxy of its own

[POS]
The decision half of the egress guard (``egress_guard.py`` is the mechanism). The default resolver resolves a host
once and admits it only when every answer is public, so the guard dials exactly the addresses that were judged.
It runs on a worker thread of the guard and does blocking DNS.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable, Sequence

from myrm_agent_harness.core.security.http.secure_fetch import parse_allowed_internal_hosts
from myrm_agent_harness.utils.url_utils import is_blocked_ip, validate_scheme_and_hostname

# (host, port) -> the addresses to dial. Raises EgressRefusedError to refuse the destination, OSError when it does not resolve.
Resolver = Callable[[str, int], Sequence[str]]

_PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy")


class EgressRefusedError(Exception):
    """The policy does not admit the destination."""


def environment_proxy_configured() -> bool:
    """True when the environment sends this process's HTTP traffic through a proxy (Chromium and libcurl both read these variables)."""
    return any(os.environ.get(name) or os.environ.get(name.upper()) for name in _PROXY_VARIABLES)


def resolve_public_addresses(host: str, port: int) -> tuple[str, ...]:
    """The addresses ``host`` names, provided the SSRF policy admits every one of them.

    The cloud policy of the fetch tiers applied to one connection: the hostname rules of ``validate_scheme_and_hostname``,
    then every address (the host itself when it is a literal) must pass ``is_blocked_ip``. A host the operator listed in
    ``MYRM_ALLOWED_INTERNAL_HOSTS`` keeps its internal answers, as it does for the fetch tiers.

    Raises:
        EgressRefusedError: the policy does not admit the host or one of its addresses.
        OSError: the name does not resolve.
    """
    canonical, error = validate_scheme_and_hostname(f"http://{f'[{host}]' if ':' in host else host}/")
    if canonical is None:
        raise EgressRefusedError(error)
    try:
        addresses: tuple[str, ...] = (str(ipaddress.ip_address(host)),)
    except ValueError:
        answers = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        addresses = tuple(dict.fromkeys(str(answer[4][0]) for answer in answers))
    if canonical not in parse_allowed_internal_hosts():
        blocked = next((address for address in addresses if is_blocked_ip(address)), None)
        if blocked is not None:
            raise EgressRefusedError(f"{host} is or resolves to the non-public address {blocked}")
    return addresses
