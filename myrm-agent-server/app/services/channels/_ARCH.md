# services/channels/

## Overview

Business-layer helpers for optional channel SDK installation and post-install gateway registration.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `dependency_install.py` | Core | Lazy pip install via harness `lazy_deps`; preflight before enable | ✅ |
| `sdk_registration.py` | Core | Hot-register DISABLED channel on bus; merge diagnostic issues | ✅ |

## Dependencies

- `dependency_install.py` → `myrm_agent_harness.runtime.lazy_deps`, `app.channels.providers.registry`
- Optional capability extras (e.g. WeChat voice `platform.wechat-silk`) install via explicit Settings action; WARNING issues do not block channel enable.
- `sdk_registration.py` → `app.channels.core.factory`, `app.core.channel_bridge`
- `api/channels/router.py` → both modules above
