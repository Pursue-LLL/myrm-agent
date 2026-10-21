"""Extension CDP relay — loopback DevTools façade for Playwright connect_over_cdp."""

from .manager import CdpRelayManager, get_cdp_relay_manager

__all__ = ["CdpRelayManager", "get_cdp_relay_manager"]
