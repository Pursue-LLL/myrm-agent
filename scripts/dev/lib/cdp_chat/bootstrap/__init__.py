"""Chat shell bootstrap and hydration workflow.

`CdpChatBootstrap` is built as a chain of layers, each in its own module and extending the one before it; a layer calls
only members of its own and of earlier layers: clock, binding, shell_ready, layout, surface, flow. This module exports
the composed class. A patch reaches only the readers of the module it is applied to, so a test patches the layer that
reads the name (`cdp_chat.bootstrap.shell_ready._bootstrap_shell_heal_wall_cap_sec`), not this module.
"""

from __future__ import annotations

from cdp_chat.bootstrap.flow import CdpChatBootstrap

__all__ = ["CdpChatBootstrap"]
