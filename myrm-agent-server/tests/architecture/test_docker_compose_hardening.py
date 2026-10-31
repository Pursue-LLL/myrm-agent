"""The local Docker stack keeps its container hardening.

[INPUT]
- docker-compose.yaml: the ``backend`` and ``frontend`` services
- app.services.agent.gateway::AgentGateway (POS: owns the in-flight turn drain budget used at shutdown)

[OUTPUT]
- Fails when the backend loses its privilege limits, its init process or a stop grace period that outlasts the turn
  drain, or when the frontend loses capability dropping, the read-only root filesystem or the locked-down /tmp.

[POS]
tests/architecture/test_docker_compose_hardening.py - guard for the hardening of docker-compose.yaml. A container
that runs a model-driven agent keeps only the privileges it needs, and a stop signal never kills a turn that is
still draining; both are silent when removed, so they are pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.services.agent.gateway import AgentGateway

pytestmark = pytest.mark.architecture

_COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yaml"
# The steps after the drain (tunnel, watchers, database) need their own time before SIGKILL.
_SHUTDOWN_MARGIN_SECONDS = 30
_NO_NEW_PRIVILEGES = "no-new-privileges:true"
_BACKEND_DROPPED_CAPS = frozenset({"NET_RAW", "NET_ADMIN", "SYS_ADMIN", "MKNOD"})


def _service(name: str) -> dict[str, object]:
    raw = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
    service = raw["services"][name]
    assert isinstance(service, dict)
    return service


def _seconds(duration: object) -> int:
    """A Compose duration such as ``150s`` or ``2m30s`` in seconds."""
    assert isinstance(duration, str), f"stop_grace_period must be a duration string, got {duration!r}"
    units = {"h": 3600, "m": 60, "s": 1}
    parts = re.findall(r"(\d+)([hms])", duration)
    assert parts and "".join(f"{n}{u}" for n, u in parts) == duration, f"unparsable duration {duration!r}"
    return sum(int(n) * units[u] for n, u in parts)


def test_backend_drops_privileges_it_does_not_need() -> None:
    backend = _service("backend")
    assert _BACKEND_DROPPED_CAPS <= set(backend.get("cap_drop", []))
    assert _NO_NEW_PRIVILEGES in backend.get("security_opt", [])


def test_backend_runs_under_an_init_process() -> None:
    assert _service("backend").get("init") is True


def test_backend_stop_grace_outlasts_the_turn_drain() -> None:
    grace = _seconds(_service("backend").get("stop_grace_period"))
    drain = int(AgentGateway._DRAIN_TIMEOUT_DEFAULT)
    assert grace >= drain + _SHUTDOWN_MARGIN_SECONDS, (
        f"stop_grace_period {grace}s must exceed the {drain}s turn drain by {_SHUTDOWN_MARGIN_SECONDS}s, "
        "or Docker kills the backend while turns are still draining"
    )


def test_frontend_drops_all_capabilities_and_privilege_escalation() -> None:
    frontend = _service("frontend")
    assert frontend.get("cap_drop") == ["ALL"]
    assert _NO_NEW_PRIVILEGES in frontend.get("security_opt", [])


def test_frontend_root_filesystem_is_read_only_with_a_locked_down_tmp() -> None:
    frontend = _service("frontend")
    assert frontend.get("read_only") is True
    tmp_mounts = [str(mount) for mount in frontend.get("tmpfs", []) if str(mount).split(":", 1)[0] == "/tmp"]
    assert len(tmp_mounts) == 1, "the frontend needs exactly one tmpfs mount at /tmp"
    options = set(tmp_mounts[0].split(":", 1)[1].split(","))
    assert {"noexec", "nosuid"} <= options
