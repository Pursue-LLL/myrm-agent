"""Endpoint reachability probes and health-payload verdicts for Chrome MCP E2E.

[INPUT]
- `HealthJsonPayload` assembled by `runtime_identity.build_health_json()` (POS: unified health snapshot)
- TCP connects, HTTP GETs and `lsof` / `ps` look-ups against the UI and API ports (POS: port-truth SSOT for who serves the stack)
- e2e_core.dev_ports::current_backend_port / shared_backend_port (POS: Default ports of the user, shared dev and isolated stacks — SSOT)

[OUTPUT]
- `attach_health_errors()` / `read_attach_health_errors()` / `signoff_stream_holder_health_errors()` / `stack_core_health_errors()`: reasons a health payload is unsafe for the respective lane
- `attach_endpoint_errors()` / `attach_wait_errors()` / `api_health_errors()` / `classify_ui_endpoint_error()` / `frontend_tcp_html_probe_ok()`: live UI and API probes
- `foreign_backend_port_owner_description()` / `backend_port_owner_is_dev_backend()` / `tcp_port_owner_pid()`: backend-port ownership
- `format_attach_endpoint_failure()`: human-facing failure text (`STACK_UI_HALF_DEAD`, `STACK_FOREIGN_LISTENER`)

[POS]
Dev infrastructure. Judges whether a running stack can be attached to; observes the stack, never mutates it.
"""

from __future__ import annotations

import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from e2e_core.dev_ports import current_backend_port, shared_backend_port
from e2e_core.runtime_types import HealthJsonPayload


def attach_health_errors(payload: HealthJsonPayload) -> list[str]:
    """Return every reason a read-only parallel attach is unsafe."""
    errors: list[str] = []
    if payload["muxDaemons"] != 1:
        errors.append(f"muxDaemons={payload['muxDaemons']}")
    checks = (
        ("upstreamReady", payload["upstreamReady"]),
        ("wsStampMatch", payload["wsStampMatch"]),
        ("shellHot", payload["shellHot"]),
        ("clientHot", payload["clientHot"]),
    )
    errors.extend(f"{name}=false" for name, ready in checks if not ready)
    if not payload["runtimeId"]:
        errors.append("runtimeId=empty")
    epochs = (
        ("backendEpoch", payload["backendEpoch"]),
        ("frontendEpoch", payload["frontendEpoch"]),
        ("chromeEpoch", payload["chromeEpoch"]),
        ("muxEpoch", payload["muxEpoch"]),
    )
    errors.extend(f"{name}=missing" for name, epoch in epochs if epoch is None)
    return errors


def signoff_stream_holder_health_errors(payload: HealthJsonPayload) -> list[str]:
    """Signoff desktop stream-lock client_hot under parallel load.

    UI compile warmth and frontendEpoch may be deferred by SMP; pytest ADMIT hydrates.
    Require mux/CDP/backend identity only.
    """
    errors: list[str] = []
    if payload["muxDaemons"] != 1:
        errors.append(f"muxDaemons={payload['muxDaemons']}")
    for name, ready in (
        ("upstreamReady", payload["upstreamReady"]),
        ("wsStampMatch", payload["wsStampMatch"]),
    ):
        if not ready:
            errors.append(f"{name}=false")
    if not payload["runtimeId"]:
        errors.append("runtimeId=empty")
    for name, epoch in (
        ("backendEpoch", payload["backendEpoch"]),
        ("chromeEpoch", payload["chromeEpoch"]),
        ("muxEpoch", payload["muxEpoch"]),
    ):
        if epoch is None:
            errors.append(f"{name}=missing")
    return errors


def _read_attach_cdp_live(payload: HealthJsonPayload) -> bool:
    """True when mux CDP identity is live for READ attach.

    ``upstreamReady`` can flap false while mux reconnects under parallel load;
    ``wsStampMatch`` + chrome/mux epochs prove the stamped CDP endpoint is current.
    """
    if payload["upstreamReady"]:
        return True
    return (
        payload["wsStampMatch"]
        and payload["chromeEpoch"] is not None
        and payload["muxEpoch"] is not None
    )


def read_attach_health_errors(payload: HealthJsonPayload) -> list[str]:
    """READ lane attach without shared_hot — mux/backend/chrome live; SMP may defer frontendEpoch."""
    errors: list[str] = []
    if payload["muxDaemons"] != 1:
        errors.append(f"muxDaemons={payload['muxDaemons']}")
    if not payload["wsStampMatch"]:
        errors.append("wsStampMatch=false")
    if not _read_attach_cdp_live(payload):
        errors.append("upstreamReady=false")
    if not payload["runtimeId"]:
        errors.append("runtimeId=empty")
    for name, epoch in (
        ("backendEpoch", payload["backendEpoch"]),
        ("chromeEpoch", payload["chromeEpoch"]),
        ("muxEpoch", payload["muxEpoch"]),
    ):
        if epoch is None:
            errors.append(f"{name}=missing")
    return errors


def stack_core_health_errors(payload: HealthJsonPayload) -> list[str]:
    """Stack liveness for stack-core keepalive — ignore compile-time shell/client warmth."""
    errors: list[str] = []
    if payload["muxDaemons"] != 1:
        errors.append(f"muxDaemons={payload['muxDaemons']}")
    for name, ready in (
        ("upstreamReady", payload["upstreamReady"]),
        ("wsStampMatch", payload["wsStampMatch"]),
    ):
        if not ready:
            errors.append(f"{name}=false")
    if not payload["runtimeId"]:
        errors.append("runtimeId=empty")
    for name, epoch in (
        ("backendEpoch", payload["backendEpoch"]),
        ("frontendEpoch", payload["frontendEpoch"]),
        ("chromeEpoch", payload["chromeEpoch"]),
        ("muxEpoch", payload["muxEpoch"]),
    ):
        if epoch is None:
            errors.append(f"{name}=missing")
    return errors


def _http_url_ok(url: str, *, timeout_sec: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as response:
            return 200 <= response.status < 300
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


def _frontend_tcp_port_listening(host: str, port: int) -> bool:
    """True when something is LISTEN on port (lsof SSOT on macOS/Linux)."""
    try:
        result = subprocess.run(
            ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def tcp_port_owner_pid(port: int) -> int | None:
    """The pid LISTENing on a TCP port (lsof is the port-truth SSOT)."""
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        candidate = line.strip()
        if candidate.isdigit():
            return int(candidate)
    return None


def _backend_port_owner(*, port: int | None = None) -> tuple[int | None, str]:
    """The backend port's owning pid and command (lsof/ps are the port-truth SSOT)."""
    backend_port = port if port is not None else current_backend_port()
    owner = tcp_port_owner_pid(backend_port)
    if owner is None:
        return None, ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(owner), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return owner, ""
    return owner, (result.stdout or "").strip()


def foreign_backend_port_owner_description(
    *, port: int | None = None, runtime_id: str | None = None
) -> str:
    """Describe a backend port owner this dev stack did not start (empty when it is ours).

    The desktop app's bundled server also listens on the backend port and answers health checks
    with 200 while serving a different database. The dev stack must neither reclaim nor adopt a
    foreign port owner, so a lane that only asks "is the API up?" silently runs against the wrong
    backend and fails for reasons that have nothing to do with the test. Ownership is the dev
    stamp in the process environment: the desktop sidecar runs the very same ``run.py`` command
    as the dev backend, so the command line proves nothing.
    """
    from e2e_core.dev_ownership import classify

    backend_port = port if port is not None else current_backend_port()
    owner, command = _backend_port_owner(port=backend_port)
    if owner is None:
        return ""
    namespace = (runtime_id or os.environ.get("MYRM_RUNTIME_NAMESPACE", "")).strip() or "shared"
    verdict = classify(owner, namespace)
    if verdict == "owned":
        return ""
    return (
        f":{backend_port} is served by pid {owner} ({command[:160]}), which this dev stack "
        f"(runtime={namespace}) did not start [ownership={verdict}]"
    )


def backend_port_owner_is_dev_backend(*, port: int | None = None) -> bool:
    """Whether the backend port is served by the dev backend (or nobody yet)."""
    return not foreign_backend_port_owner_description(port=port)


def _ui_probe_host_port(ui_base: str) -> tuple[str, int]:
    parsed = urlparse(ui_base)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme == "https":
        port = 443
    else:
        port = 80
    return host, port


def frontend_tcp_html_probe_ok(ui_base: str, *, timeout_sec: float = 5.0) -> bool:
    """W2 #4 dual probe: fresh TCP connect + first-HTML-packet on the shared UI.

    Guards against "probe before=ok but curl refused": a keep-alive
    HTTP 200 can be served by a dying Next process while a fresh TCP connect is
    refused, and a listening socket can accept without ever speaking HTML.
    Requires a NEW socket connection whose first response packets carry an HTML
    document, so a cached ``urlopen`` 200 can never fake liveness.
    """
    import socket
    import ssl

    parsed = urlparse(ui_base)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_sec) as raw:
            sock: socket.socket | ssl.SSLSocket = raw
            if parsed.scheme == "https":
                context = ssl.create_default_context()
                sock = context.wrap_socket(raw, server_hostname=host)
            with sock:
                sock.settimeout(timeout_sec)
                sock.sendall(
                    (
                        f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
                        "Connection: close\r\nAccept: text/html\r\n\r\n"
                    ).encode("ascii")
                )
                buffered = bytearray()
                while len(buffered) < 65_536:
                    try:
                        chunk = sock.recv(4096)
                    except TimeoutError:
                        break
                    if not chunk:
                        break
                    buffered.extend(chunk)
                    lowered = buffered.lower()
                    if b"<!doctype html" in lowered or b"<html" in lowered:
                        return True
    except (OSError, TimeoutError, ValueError, ssl.SSLError):
        return False
    return False


def classify_ui_endpoint_error(ui_base: str, *, timeout_sec: float = 5.0) -> str | None:
    """Return ui error token or None when UI serves real HTML (W2 #4 SSOT)."""
    if frontend_tcp_html_probe_ok(ui_base, timeout_sec=timeout_sec):
        return None
    _, port = _ui_probe_host_port(ui_base)
    if _frontend_tcp_port_listening("127.0.0.1", port):
        return "ui=half_dead"
    return "ui=unreachable"


API_FOREIGN_LISTENER = "api=foreign_listener"


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def format_attach_endpoint_failure(errors: list[str]) -> str:
    """Human-facing attach failure with STACK_UI_HALF_DEAD / STACK_FOREIGN_LISTENER guidance."""
    if any(error.strip() == API_FOREIGN_LISTENER for error in errors):
        return (
            "STACK_FOREIGN_LISTENER: the shared API port answers health but is held by a process "
            "this dev stack did not start (the desktop app's sidecar or a `myrm start` runtime, "
            "serving the user's own data) — attach refuses to test against it, and no dev command "
            "restarts or adopts it. Stop that process yourself, or run on an isolated runtime: "
            "./myrm-dev isolate"
        )
    if any(error.strip() == "ui=half_dead" for error in errors):
        return (
            "STACK_UI_HALF_DEAD: shared UI listening but HTTP unreachable — "
            "ADMIT queue waited; when wave_leases=0 run: ./myrm-dev restart --chrome "
            "(do not stop other pytest)"
        )
    return "CHROME_E2E_ATTACH_NOT_READY: " + ", ".join(errors)


def _api_endpoint_error(api_base: str, *, timeout_sec: float) -> str | None:
    """`api=unreachable` | `api=foreign_listener` | None (healthy and ours).

    Only the shared dev API port is checked for ownership: a user's runtime sits on that default
    port, whereas private/pinned runtime ports are allocated by the dev tooling itself.
    """
    if not _http_url_ok(api_base.rstrip("/") + "/api/v1/health", timeout_sec=timeout_sec):
        return "api=unreachable"
    host, port = _ui_probe_host_port(api_base)
    if (
        host in _LOOPBACK_HOSTS
        and port == shared_backend_port()
        and foreign_backend_port_owner_description(port=port, runtime_id="shared")
    ):
        return API_FOREIGN_LISTENER
    return None


def api_health_errors(api_base: str) -> list[str]:
    """Probe API health only — used by stack-core keepalive."""
    api_timeout = 10.0 if os.getenv("MYRM_E2E_ISOLATED") == "1" else 5.0
    error = _api_endpoint_error(api_base, timeout_sec=api_timeout)
    return [] if error is None else [error]


def shpoib_private_backend_preflight() -> bool:
    """True when attach preflight runs for SHPOIB private-backend chrome_e2e."""
    return os.getenv("MYRM_PRIVATE_BACKEND", "").strip() == "1"


def filter_shpoib_attach_wait_errors(errors: list[str]) -> list[str]:
    """Drop shared api=* errors for SHPOIB ADMIT wait (private pool binds later)."""
    if not shpoib_private_backend_preflight():
        return errors
    return [error for error in errors if not error.strip().startswith("api=")]


def attach_wait_errors(ui_base: str, api_base: str) -> list[str]:
    """Attach ADMIT wait probe; SHPOIB ignores flaky shared backend under parallel load."""
    return filter_shpoib_attach_wait_errors(attach_endpoint_errors(ui_base, api_base))


def attach_endpoint_errors(ui_base: str, api_base: str) -> list[str]:
    """Probe UI and API concurrently for the attach-only fast path."""
    from dev_gate.contract import attach_ui_probe_timeout_sec

    ui_timeout = attach_ui_probe_timeout_sec()
    api_timeout = 10.0 if os.getenv("MYRM_E2E_ISOLATED") == "1" else 5.0

    def probe_ui() -> str | None:
        return classify_ui_endpoint_error(ui_base, timeout_sec=ui_timeout)

    def probe_api() -> str | None:
        return _api_endpoint_error(api_base, timeout_sec=api_timeout)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="attach-health") as pool:
        ui_future = pool.submit(probe_ui)
        api_future = pool.submit(probe_api)
        try:
            ui_error = ui_future.result(timeout=ui_timeout + 3.0)
        except TimeoutError:
            ui_error = "ui=probe_timeout"
        try:
            api_error = api_future.result(timeout=api_timeout + 3.0)
        except TimeoutError:
            api_error = "api=probe_timeout"
    errors: list[str] = []
    if ui_error is not None:
        errors.append(ui_error)
    if api_error is not None:
        errors.append(api_error)
    return errors
