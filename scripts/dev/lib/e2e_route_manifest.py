"""RouteManifest + HydrationGate registry — Page Navigation Plane SSOT (§19.11.10 NAV-1).

[INPUT]
app route path (e.g. ``/settings/mcp``)

[OUTPUT]
:class:`RouteManifestEntry`: shell_path · subroute · hydration_gate · requires_cold_navigate

[POS]
Single declaration table for how any app route is opened by the Browser Orchestrator.
Eliminates scattered per-test navigate helpers and gate/probe mixing (§19.11.10.0).
HydrationGate probes are the only allowed hydration probes per route class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from urllib.parse import urlsplit


class HydrationGate(str, Enum):
    """Hydration probe identity per route class (§19.11.10.2 · 禁混用)."""

    APP_LAYOUT = "app-layout"
    SETTINGS_LAYOUT = "settings-layout"
    MCP_SETTINGS = "mcp-settings"
    WIKI_SETTINGS_SHELL = "wiki-settings-shell"
    CHAT_BRIDGE = "chat-bridge"


@dataclass(frozen=True)
class RouteManifestEntry:
    """One declarative row: path prefix → open plan for the orchestrator."""

    path_prefix: str
    shell_path: str
    subroute: bool
    hydration_gate: HydrationGate
    requires_cold_navigate: bool = False


@dataclass(frozen=True)
class HydrationProbe:
    """Probe JS bound to a gate — SSOT for hydration waits."""

    gate: HydrationGate
    js: str
    forbidden_gates: tuple[HydrationGate, ...] = field(default_factory=tuple)


ROUTE_MANIFEST: tuple[RouteManifestEntry, ...] = (
    RouteManifestEntry(
        path_prefix="/settings/mcp",
        shell_path="/settings",
        subroute=True,
        hydration_gate=HydrationGate.MCP_SETTINGS,
    ),
    RouteManifestEntry(
        path_prefix="/settings/wiki",
        shell_path="/settings",
        subroute=True,
        hydration_gate=HydrationGate.WIKI_SETTINGS_SHELL,
    ),
    RouteManifestEntry(
        path_prefix="/settings",
        shell_path="/settings",
        subroute=True,
        hydration_gate=HydrationGate.SETTINGS_LAYOUT,
    ),
    RouteManifestEntry(
        path_prefix="/chats",
        shell_path="/",
        subroute=True,
        hydration_gate=HydrationGate.CHAT_BRIDGE,
    ),
    RouteManifestEntry(
        path_prefix="/",
        shell_path="/",
        subroute=False,
        hydration_gate=HydrationGate.APP_LAYOUT,
    ),
)

# Gate → forbidden gates: settings must never use chat-bridge; chat must never use settings-layout.
_GATE_FORBIDDEN_MAP: dict[HydrationGate, tuple[HydrationGate, ...]] = {
    HydrationGate.SETTINGS_LAYOUT: (HydrationGate.CHAT_BRIDGE,),
    HydrationGate.MCP_SETTINGS: (HydrationGate.CHAT_BRIDGE, HydrationGate.SETTINGS_LAYOUT),
    HydrationGate.WIKI_SETTINGS_SHELL: (
        HydrationGate.CHAT_BRIDGE,
        HydrationGate.SETTINGS_LAYOUT,
    ),
    HydrationGate.CHAT_BRIDGE: (HydrationGate.SETTINGS_LAYOUT,),
    HydrationGate.APP_LAYOUT: (HydrationGate.SETTINGS_LAYOUT,),
}

_APP_LAYOUT_PROBE = """(() => ({
  ready: !!document.querySelector('[data-testid="app-layout"]'),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'app',
}))()"""

_SETTINGS_LAYOUT_PROBE = """(() => ({
  ready:
    location.pathname.startsWith('/settings') &&
    (
      !!document.querySelector('[data-testid="settings-layout"]') ||
      (
        !!document.querySelector('aside') &&
        !!document.querySelector('[data-section][data-active]') &&
        (document.body?.innerText?.length ?? 0) > 40
      )
    ),
  deferredLoading:
    !!document.querySelector('[data-testid="settings-deferred-loading"]') ||
    !!document.querySelector('[data-testid="settings-route-loading"]'),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'settings',
}))()"""

_MCP_SETTINGS_PROBE = """(() => ({
  ready: /MCP 服务配置|MCP Service/i.test(document.body?.innerText || ''),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'mcp-settings',
}))()"""

_WIKI_SETTINGS_SHELL_PROBE = """(() => {
  const bodyText = document.body?.innerText || '';
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  const dedupTab = document.querySelector('[data-testid="wiki-dedup-tab"]');
  const layout = document.querySelector('[data-testid="app-layout"]');
  const settingsLayout = document.querySelector('[data-testid="settings-layout"]');
  const deferredLoading = document.querySelector('[data-testid="settings-deferred-loading"]');
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      !!layout &&
      !deferredLoading &&
      (!!shell || !!dedupTab),
    pathname: location.pathname,
    bodyLength: bodyText.length,
    hasShell: !!shell,
    hasDedupTab: !!dedupTab,
    hasAppLayout: !!layout,
    hasSettingsLayout: !!settingsLayout,
    hasDeferredLoading: !!deferredLoading,
  };
})()"""

_CHAT_BRIDGE_PROBE = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function'
    && window.__MYRM_E2E_CHAT__?.__e2eFallback !== true,
  hasAttach: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
  fallback: window.__MYRM_E2E_CHAT__?.__e2eFallback === true,
  hasInput: Boolean(document.querySelector('[data-chat-input]')),
  hasAppLayout: Boolean(document.querySelector('[data-testid="app-layout"]')),
  hasSkeleton: Boolean(document.querySelector('[data-testid="app-shell-skeleton"]')),
  bodyLength: (document.body?.innerText || '').length,
  href: location.href,
}))()"""

HYDRATION_PROBES: dict[HydrationGate, HydrationProbe] = {
    HydrationGate.APP_LAYOUT: HydrationProbe(
        gate=HydrationGate.APP_LAYOUT,
        js=_APP_LAYOUT_PROBE,
        forbidden_gates=_GATE_FORBIDDEN_MAP[HydrationGate.APP_LAYOUT],
    ),
    HydrationGate.SETTINGS_LAYOUT: HydrationProbe(
        gate=HydrationGate.SETTINGS_LAYOUT,
        js=_SETTINGS_LAYOUT_PROBE,
        forbidden_gates=_GATE_FORBIDDEN_MAP[HydrationGate.SETTINGS_LAYOUT],
    ),
    HydrationGate.MCP_SETTINGS: HydrationProbe(
        gate=HydrationGate.MCP_SETTINGS,
        js=_MCP_SETTINGS_PROBE,
        forbidden_gates=_GATE_FORBIDDEN_MAP[HydrationGate.MCP_SETTINGS],
    ),
    HydrationGate.WIKI_SETTINGS_SHELL: HydrationProbe(
        gate=HydrationGate.WIKI_SETTINGS_SHELL,
        js=_WIKI_SETTINGS_SHELL_PROBE,
        forbidden_gates=_GATE_FORBIDDEN_MAP[HydrationGate.WIKI_SETTINGS_SHELL],
    ),
    HydrationGate.CHAT_BRIDGE: HydrationProbe(
        gate=HydrationGate.CHAT_BRIDGE,
        js=_CHAT_BRIDGE_PROBE,
        forbidden_gates=_GATE_FORBIDDEN_MAP[HydrationGate.CHAT_BRIDGE],
    ),
}


def normalize_route_path(url_or_path: str) -> str:
    """Return a normalized, origin-stripped path prefix (e.g. ``/settings/mcp``)."""
    stripped = (url_or_path or "").strip()
    if not stripped:
        return "/"
    if stripped.startswith("http://") or stripped.startswith("https://"):
        path = urlsplit(stripped).path or "/"
    else:
        path = stripped.split("?", 1)[0].split("#", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return path


def resolve_route_manifest(url_or_path: str) -> RouteManifestEntry:
    """Longest-prefix manifest match for a path (declarative — no scattered if/else)."""
    path = normalize_route_path(url_or_path)
    best: RouteManifestEntry | None = None
    for entry in ROUTE_MANIFEST:
        if path == entry.path_prefix or path.startswith(entry.path_prefix.rstrip("/") + "/"):
            if best is None or len(entry.path_prefix) > len(best.path_prefix):
                best = entry
    if best is None:
        best = ROUTE_MANIFEST[-1]  # "/" app-layout catch-all
    # subroute is only needed when the actual path differs from the reclaim shell.
    needs_subroute = best.subroute and path != best.shell_path
    if needs_subroute == best.subroute:
        return best
    from dataclasses import replace

    return replace(best, subroute=needs_subroute)


def hydration_probe_js(gate: HydrationGate) -> str:
    """Return the probe JS bound to a gate (SSOT hydration wait expression)."""
    probe = HYDRATION_PROBES.get(gate)
    if probe is None:
        raise KeyError(f"unknown hydration gate: {gate!r}")
    return probe.js


def assert_gate_allowed(gate: HydrationGate, url_or_path: str) -> None:
    """Enforce §19.11.10.2: a gate must not be applied to a forbidden route class."""
    entry = resolve_route_manifest(url_or_path)
    # A route's declared gate declares which gates may never be used there.
    route_forbidden = _GATE_FORBIDDEN_MAP.get(entry.hydration_gate, ())
    if gate in route_forbidden:
        raise ValueError(
            f"HydrationGate mixing forbidden: gate={gate.value} "
            f"route={normalize_route_path(url_or_path)!r}"
        )
    # Symmetric check: applying the route's gate to a conflicting route class.
    gate_forbidden = _GATE_FORBIDDEN_MAP.get(gate, ())
    if entry.hydration_gate in gate_forbidden:
        raise ValueError(
            f"HydrationGate mixing forbidden: gate={gate.value} "
            f"route={normalize_route_path(url_or_path)!r}"
        )


def manifest_gate_for(url_or_path: str) -> HydrationGate:
    """Return the manifest-declared gate for a route (orchestrator hydration lookup)."""
    return resolve_route_manifest(url_or_path).hydration_gate
