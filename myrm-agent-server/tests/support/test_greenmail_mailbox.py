"""The helper that starts a real mail server removes what a killed run left behind, and reads its ports correctly.

[INPUT]
- tests/support/greenmail_mailbox.py: stale_containers, published_port

[OUTPUT]
- Fails when a container of a run that was killed long ago is kept, when one of a run that is still going or of another
  tool is removed, or when a name that does not carry a start time is taken for a stale one.
- Fails when the host port is read from anywhere but the first line of ``docker port`` output.

[POS]
Unit test of the pure part of the helper; starting the server needs Docker and is covered by the live test that uses it.
"""

from __future__ import annotations

import pytest

from tests.support.greenmail_mailbox import NAME_PREFIX, published_port, stale_containers

_NOW = 1_800_000_000


@pytest.mark.parametrize(
    ("names", "stale"),
    [
        pytest.param(
            [f"{NAME_PREFIX}{_NOW - 3600}-a1b2c3d4"], [f"{NAME_PREFIX}{_NOW - 3600}-a1b2c3d4"], id="started-an-hour-ago"
        ),
        pytest.param([f"{NAME_PREFIX}{_NOW - 60}-a1b2c3d4"], [], id="a-run-in-progress"),
        pytest.param([f"{NAME_PREFIX}{_NOW - 1800}-a1b2c3d4"], [], id="exactly-at-the-limit"),
        pytest.param(["postgres", "searxng", f"other-{NAME_PREFIX}{_NOW - 3600}-x"], [], id="other-containers"),
        pytest.param([f"{NAME_PREFIX}a1b2c3d4", f"{NAME_PREFIX}", f"{NAME_PREFIX}-x"], [], id="no-start-time"),
        pytest.param(
            [f"{NAME_PREFIX}{_NOW - 7200}-a", f"{NAME_PREFIX}{_NOW - 10}-b", f"{NAME_PREFIX}{_NOW - 4000}-c"],
            [f"{NAME_PREFIX}{_NOW - 7200}-a", f"{NAME_PREFIX}{_NOW - 4000}-c"],
            id="a-mix-keeps-the-fresh-one",
        ),
    ],
)
def test_only_the_containers_of_a_run_killed_long_ago_are_stale(names: list[str], stale: list[str]) -> None:
    assert stale_containers(names, _NOW) == stale


@pytest.mark.parametrize(
    ("shown", "port"),
    [
        pytest.param("127.0.0.1:32769\n", 32769, id="loopback-v4"),
        pytest.param("[::1]:32771\n", 32771, id="loopback-v6"),
        pytest.param("127.0.0.1:32769\n[::1]:32770\n", 32769, id="the-first-line-wins"),
    ],
)
def test_the_host_port_is_read_from_the_first_line_of_docker_port(shown: str, port: int) -> None:
    assert published_port(shown) == port
