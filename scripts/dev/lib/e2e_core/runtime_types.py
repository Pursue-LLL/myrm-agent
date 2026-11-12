"""Typed payload shapes shared by the runtime identity modules.

[INPUT]
- None (pure type declarations)

[OUTPUT]
- `BackendEpoch` / `FrontendEpoch` / `ChromeEpoch` / `MuxEpoch`: one generation record per runtime plane
- `RuntimeIdentityParts`: the four epochs a `runtimeId` is derived from
- `RuntimeProbeContext`: live probe result of `runtime_probe.probe_runtime_context()`
- `HealthJsonPayload`: shape of the unified `CHROME_E2E_HEALTH_JSON`

[POS]
Leaf of the runtime identity cluster: the epoch readers, endpoint health checks and identity composer import it; it imports none of them.
"""

from __future__ import annotations

from typing import TypedDict


class BackendEpoch(TypedDict):
    epoch: int
    backend_pid: int | None
    started_at: str
    harness_fingerprint: str
    stored_source_fingerprint: str
    workspace_source_fingerprint: str
    epoch_match: bool


class FrontendEpoch(TypedDict):
    generation: str
    source_fingerprint: str
    pid: int | None
    started_at: str
    port: int | None
    bundler_mode: str


class ChromeEpoch(TypedDict):
    cdp_port: int
    browser_id: str
    web_socket_url: str
    profile_dir: str


class MuxEpoch(TypedDict):
    daemon_pid: int | None
    ws_url: str
    upstream_ready: bool
    upstream_generation: int


class RuntimeIdentityParts(TypedDict):
    backend_epoch: BackendEpoch | None
    frontend_epoch: FrontendEpoch | None
    chrome_epoch: ChromeEpoch | None
    mux_epoch: MuxEpoch | None


class RuntimeProbeContext(TypedDict):
    mux_daemon_count: int
    upstream_ready: bool
    upstream_generation: int
    ws_stamp_matches: bool
    frontend_dir: str
    cdp_port: int
    profile_dir: str


class HealthJsonPayload(TypedDict):
    ui: str
    api: str
    muxDaemons: int
    upstreamReady: bool
    wsStampMatch: bool
    shellHot: bool
    clientHot: bool
    stackEpoch: int | None
    attachMode: bool
    runtimeId: str
    backendEpoch: BackendEpoch | None
    frontendEpoch: FrontendEpoch | None
    chromeEpoch: ChromeEpoch | None
    muxEpoch: MuxEpoch | None
