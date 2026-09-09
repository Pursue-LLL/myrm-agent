"""Tailscale node discovery and zero-trust remote access service.

[INPUT]
- System tailscale CLI (`tailscale status --json`)
- Local network state and daemon connectivity

[OUTPUT]
- TailscaleNodeInfo dataclass with IP, MagicDNS FQDN, node name, and serve URL
- probe_tailscale_status() async probe with TTL cache and timeout protection

[POS]
Backend service powering Tailscale zero-trust remote access detection and UI cards.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from typing import Final

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL_SECONDS: Final[float] = 15.0
_PROBE_TIMEOUT_SECONDS: Final[float] = 2.0

_COMMON_TAILSCALE_PATHS: Final[tuple[str, ...]] = (
    "/opt/Homebrew/bin/tailscale",
    "/usr/local/bin/tailscale",
    "/usr/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
)


@dataclass(frozen=True, slots=True)
class TailscaleNodeInfo:
    """State and identity metadata discovered from the local Tailscale client."""

    installed: bool
    running: bool
    ips: tuple[str, ...] = field(default_factory=tuple)
    fqdn: str | None = None
    node_name: str | None = None
    tailnet: str | None = None
    user: str | None = None
    serve_url: str | None = None


_cached_info: TailscaleNodeInfo | None = None
_cached_at: float = 0.0
_probe_lock = asyncio.Lock()


def find_tailscale_binary() -> str | None:
    """Find the path to the tailscale CLI executable."""
    found = shutil.which("tailscale")
    if found:
        return found
    for path in _COMMON_TAILSCALE_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def parse_tailscale_serve_status_json(raw_json: str) -> bool:
    """Check if `tailscale serve` has active proxy or HTTPS handlers configured."""
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    web_config = data.get("Web")
    if isinstance(web_config, dict) and len(web_config) > 0:
        return True
    tcp_config = data.get("TCP")
    if isinstance(tcp_config, dict) and len(tcp_config) > 0:
        return True
    return False


async def probe_tailscale_serve_active(
    binary: str,
    *,
    timeout_seconds: float = 1.0,
) -> bool:
    """Check if `tailscale serve` is actively forwarding traffic."""
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "serve",
            "status",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_seconds,
        )
        if proc.returncode == 0:
            raw_text = stdout_bytes.decode("utf-8", errors="replace")
            return parse_tailscale_serve_status_json(raw_text)
        return False
    except (asyncio.TimeoutError, TimeoutError, OSError):
        return False


def parse_tailscale_status_json(
    raw_json: str,
    *,
    serve_active: bool = False,
) -> TailscaleNodeInfo:
    """Parse JSON output from `tailscale status --json` into TailscaleNodeInfo."""
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError, ValueError) as err:
        logger.debug("Failed to decode tailscale JSON: %s", err)
        return TailscaleNodeInfo(installed=True, running=False)

    backend_state = data.get("BackendState", "")
    is_running = backend_state == "Running"

    self_node = data.get("Self", {})
    raw_ips = self_node.get("TailscaleIPs", [])
    ips: tuple[str, ...] = tuple(str(ip) for ip in raw_ips if isinstance(ip, str))

    raw_dns = self_node.get("DNSName", "")
    fqdn: str | None = raw_dns.rstrip(".") if raw_dns else None

    raw_node_name = self_node.get("HostName", "")
    node_name: str | None = raw_node_name if raw_node_name else None

    # Derive tailnet name from FQDN e.g. "mymac.shark-fin.ts.net" -> "shark-fin"
    tailnet: str | None = None
    if fqdn and fqdn.endswith(".ts.net"):
        parts = fqdn[:-7].split(".")
        if len(parts) >= 2:
            tailnet = parts[-1]

    # Extract authenticated user login from User mapping
    user_id = self_node.get("UserID")
    user: str | None = None
    if user_id is not None:
        user_profiles = data.get("User", {})
        user_dict = user_profiles.get(str(user_id)) or user_profiles.get(user_id)
        if isinstance(user_dict, dict):
            user = user_dict.get("LoginName") or user_dict.get("DisplayName")

    serve_url: str | None = f"https://{fqdn}" if (fqdn and is_running and serve_active) else None

    return TailscaleNodeInfo(
        installed=True,
        running=is_running,
        ips=ips,
        fqdn=fqdn,
        node_name=node_name,
        tailnet=tailnet,
        user=user,
        serve_url=serve_url,
    )


async def probe_tailscale_status(
    *,
    timeout_seconds: float = _PROBE_TIMEOUT_SECONDS,
    cache_ttl_seconds: float = _DEFAULT_CACHE_TTL_SECONDS,
    use_cache: bool = True,
) -> TailscaleNodeInfo:
    """Probe the local Tailscale daemon status with timeout protection and TTL caching."""
    global _cached_info, _cached_at

    now = time.monotonic()
    if use_cache and _cached_info is not None and (now - _cached_at) < cache_ttl_seconds:
        return _cached_info

    async with _probe_lock:
        now = time.monotonic()
        if use_cache and _cached_info is not None and (now - _cached_at) < cache_ttl_seconds:
            return _cached_info

        binary = find_tailscale_binary()
        if not binary:
            info = TailscaleNodeInfo(installed=False, running=False)
            _cached_info = info
            _cached_at = now
            return info

        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                "status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            if proc.returncode == 0:
                raw_text = stdout_bytes.decode("utf-8", errors="replace")
                base_info = parse_tailscale_status_json(raw_text, serve_active=False)
                serve_active = False
                if base_info.running and base_info.fqdn:
                    serve_active = await probe_tailscale_serve_active(
                        binary,
                        timeout_seconds=min(1.0, timeout_seconds),
                    )
                info = parse_tailscale_status_json(raw_text, serve_active=serve_active)
            else:
                info = TailscaleNodeInfo(installed=True, running=False)
        except (asyncio.TimeoutError, TimeoutError):
            logger.debug("Tailscale status probe timed out after %.1fs", timeout_seconds)
            info = _cached_info or TailscaleNodeInfo(installed=True, running=False)
        except OSError as err:
            logger.debug("Failed to execute tailscale CLI: %s", err)
            info = TailscaleNodeInfo(installed=True, running=False)

        _cached_info = info
        _cached_at = time.monotonic()
        return info


def get_cached_tailscale_status() -> TailscaleNodeInfo | None:
    """Return the cached TailscaleNodeInfo if available without triggering I/O."""
    return _cached_info


def clear_tailscale_cache_for_testing() -> None:
    """Reset the module-level probe cache for test isolation."""
    global _cached_info, _cached_at
    _cached_info = None
    _cached_at = 0.0


__all__ = [
    "TailscaleNodeInfo",
    "clear_tailscale_cache_for_testing",
    "find_tailscale_binary",
    "get_cached_tailscale_status",
    "parse_tailscale_serve_status_json",
    "parse_tailscale_status_json",
    "probe_tailscale_serve_active",
    "probe_tailscale_status",
]
