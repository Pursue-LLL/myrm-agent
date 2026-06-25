# services/local_browser/

## Overview

Server-layer local browser data search (Chrome/Edge bookmarks and history). Loaded only when `is_local_mode()` is true. Implementation lives entirely in this package — not in harness `toolkits/`.

## File Index

| File | Role |
|------|------|
| `local_browser_data_agent_tools.py` | `create_local_browser_data_tool` → `browser_local_search_tool` |
| `chromium_locator.py` | Discover installed Chromium-based browsers |
| `profile_enumerator.py` | Enumerate browser profiles |
| `bookmark_searcher.py` | Search bookmark databases |
| `history_searcher.py` | Search history databases |
| `types.py` | Shared search types |

## Registration

- Tool layer: `app/ai_agents/general_agent/tools/_tool_layer_bootstrap.py` (`browser_local_search_tool`)
- Load path: `tool_setup.py::_setup_local_browser_data_tool` (import from this package)
- Gate: `factory.py` calls setup only when `is_local_mode()` is true
