"""Global browser resource pool — zero-copy page reuse, intelligent scheduling, proxy rotation.

[OUTPUT]
- GlobalBrowserPool: global browser pool with zero-copy page reuse
- PagePool: per-context page object pool
- ContextType: context purpose classification (CRAWL/AGENT/STEALTH)
- BrowserMode: browser runtime mode enum
- EmulationConfig: type-safe browser environment emulation config
- ProxyConfig: proxy server config
- ProxyPool: proxy pool protocol (supports rotation and sticky sessions)
- RoundRobinProxyPool: default round-robin proxy pool implementation
- EgressGuard: loopback SOCKS5 proxy that lets launched browsers connect only to addresses the SSRF policy admits
- EgressGuardError: a browser that does not route through the guard, or a guard that was stopped
- create_egress_guard: the guard for this process's browsers, or None where the SSRF policy cannot be applied to connections
- ExtensionBridge: Protocol for browser extension CDP proxy integration
- ExtensionTab: data class for tabs exposed by extension
- ExtensionStatus: real-time extension connection status
- ExtensionBridgeNotAvailableError: exception when extension is not connected
- get_global_browser_pool: get global browser pool singleton
- reset_global_browser_pool_for_tests: shut down and clear pool singleton (test teardown)

[POS]
Global browser resource pool. Manages Browser/Context/Page three-layer resources, implementing zero-copy page reuse,
smart load scheduling, type-based isolation (CRAWL/AGENT/STEALTH), proxy rotation and sticky sessions.
The egress guard names resolve on first access: the guard brings in the HTTP client and the security detection
stack, which importing the pool must not pay for.
"""

from importlib import import_module as _import_module
from typing import TYPE_CHECKING

from ..exceptions import BrowserLaunchError, BrowserPoolError
from .browser_launcher import BrowserInstance, BrowserLauncher
from .browser_pool import (
    ContextType,
    GlobalBrowserPool,
)
from .chrome_prompt_guard import (
    ChromePromptGuard,
    approve_chrome_remote_debugging_prompt,
    is_accessibility_trusted,
    watch_chrome_remote_debugging_prompt,
)
from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerCallback,
    CircuitBreakerOpenError,
    LoggingCallback,
)
from .config import (
    BrowserConfig,
    BrowserMode,
    BrowserPoolConfig,
    CircuitBreakerConfig,
    HumanizeConfig,
    HumanizeMode,
    LaunchMode,
    MemoryGuardConfig,
    RateLimiterConfig,
    ResourceBlockConfig,
    RobustnessPolicy,
    ThrottleMode,
)
from .context_factory import ContextFactory
from .emulation import EmulationConfig
from .extension_bridge import (
    ExtensionBridge,
    ExtensionBridgeNotAvailable,
    ExtensionBridgeNotAvailableError,
    ExtensionStatus,
    ExtensionTab,
)
from .page_pool import PagePool
from .proxy import ProxyConfig, ProxyPool, RoundRobinProxyPool
from .singleton import get_global_browser_pool, reset_global_browser_pool_for_tests

if TYPE_CHECKING:
    from .egress_guard import EgressGuard, EgressGuardError, create_egress_guard

_EXPORTS: dict[str, tuple[str, str]] = {
    "EgressGuard": (".egress_guard", "EgressGuard"),
    "EgressGuardError": (".egress_guard", "EgressGuardError"),
    "create_egress_guard": (".egress_guard", "create_egress_guard"),
}

__all__ = [
    "BrowserConfig",
    "BrowserInstance",
    "BrowserLaunchError",
    "BrowserLauncher",
    "BrowserMode",
    "BrowserPoolConfig",
    "BrowserPoolError",
    "ChromePromptGuard",
    "CircuitBreaker",
    "CircuitBreakerCallback",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "ContextFactory",
    "ContextType",
    "EgressGuard",
    "EgressGuardError",
    "EmulationConfig",
    "ExtensionBridge",
    "ExtensionBridgeNotAvailable",
    "ExtensionBridgeNotAvailableError",
    "ExtensionStatus",
    "ExtensionTab",
    "GlobalBrowserPool",
    "HumanizeConfig",
    "HumanizeMode",
    "LaunchMode",
    "LoggingCallback",
    "MemoryGuardConfig",
    "PagePool",
    "ProxyConfig",
    "ProxyPool",
    "RateLimiterConfig",
    "ResourceBlockConfig",
    "RobustnessPolicy",
    "RoundRobinProxyPool",
    "ThrottleMode",
    "approve_chrome_remote_debugging_prompt",
    "create_egress_guard",
    "get_global_browser_pool",
    "is_accessibility_trusted",
    "reset_global_browser_pool_for_tests",
    "watch_chrome_remote_debugging_prompt",
]


def __getattr__(name: str) -> object:
    try:
        module_path, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    value = getattr(_import_module(module_path, __name__), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__ + [name for name in globals() if not name.startswith("_")]))
