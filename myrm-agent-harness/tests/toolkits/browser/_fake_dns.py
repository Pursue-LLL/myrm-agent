"""Fake hostnames for real-Chromium tests: the process resolver answers them from a table, Chromium dials loopback.

[INPUT]
- stdlib socket (POS: the process resolver the SSRF policy asks)
- toolkits.browser.pool.browser_pool::_DEFAULT_LAUNCH_OPTIONS (POS: the launch options a pool starts Chromium with)
- tests.toolkits.browser._redirect_servers::Site (POS: a loopback test server)

[OUTPUT]
- process_dns: context manager answering fake hostnames from a table (and failing others on request)
- launch_options_dialing_loopback: Chromium launch options that connect the given hostnames to 127.0.0.1
- url_on: a loopback site's URL under a fake hostname

[POS]
Test support that models an attacker-controlled (or merely odd) DNS answer. The SSRF policy reads the table's answer
while Chromium really connects to the loopback test server, so a request the policy lets through lands for real and
one it refuses can be proven never to have reached the server (see ``_redirect_servers``).
"""

from __future__ import annotations

import socket
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from unittest.mock import patch

from myrm_agent_harness.toolkits.browser.pool.browser_pool import _DEFAULT_LAUNCH_OPTIONS
from tests.toolkits.browser._redirect_servers import Site

type _AddrInfo = Sequence[
    tuple[
        socket.AddressFamily,
        socket.SocketKind,
        int,
        str,
        tuple[str, int] | tuple[str, int, int, int] | tuple[int, bytes],
    ]
]


@contextmanager
def process_dns(answers: Mapping[str, str], *, unresolvable: Collection[str] = ()) -> Iterator[None]:
    """Answer the hostnames in ``answers`` from the table and fail ``unresolvable`` ones; every other lookup stays real."""
    real = socket.getaddrinfo

    def answer(
        host: str | bytes | None,
        port: str | bytes | int | None,
        family: int = 0,
        kind: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> _AddrInfo:
        name = host.decode() if isinstance(host, bytes) else host
        if name is not None:
            if name in unresolvable:
                raise socket.gaierror(socket.EAI_NONAME, "unresolvable in the test")
            if name in answers:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (answers[name], 0))]
        return real(host, port, family, kind, proto, flags)

    with patch.object(socket, "getaddrinfo", answer):
        yield


def launch_options_dialing_loopback(hosts: Iterable[str]) -> dict[str, object]:
    """Chromium launch options that connect every hostname in ``hosts`` to 127.0.0.1, whatever the resolver says."""
    default_args = _DEFAULT_LAUNCH_OPTIONS["args"]
    assert isinstance(default_args, list)
    mapping = ", ".join(f"MAP {host} 127.0.0.1" for host in hosts)
    return {**_DEFAULT_LAUNCH_OPTIONS, "args": [*default_args, f"--host-resolver-rules={mapping}"]}


def url_on(host: str, site: Site, path: str = "/") -> str:
    """``site`` (a loopback server) under the fake hostname ``host``."""
    return f"http://{host}:{site.base_url.rsplit(':', 1)[1]}{path}"
