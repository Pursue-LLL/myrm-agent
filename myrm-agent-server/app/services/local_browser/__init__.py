"""Local browser data search — server-layer product capability.

Reads the user's local Chrome/Edge bookmarks and browsing history.
Only loaded in local/desktop deploy mode.
"""

from .local_browser_data_agent_tools import create_local_browser_data_tool

__all__ = ["create_local_browser_data_tool"]
