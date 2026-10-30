# services/channels/

## Overview

Business-layer helpers for optional channel SDK installation and post-install gateway registration.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `dependency_install.py` | Core | Lazy pip install via harness `lazy_deps`; preflight before enable | ✅ |
| `cp_egress_client.py` | Core | Sandbox-to-CP outbound bridge; success requires CP `message_id` in response | ✅ |
| `sdk_registration.py` | Core | Hot-register DISABLED channel on bus; merge diagnostic issues | ✅ |
| `credential_reload.py` | Core | `CREDENTIAL_KEY_TO_CHANNEL` (config key of a credentials save → channel) and `reload_channel_credentials`: rebuild the channel from its saved credentials and swap it into the gateway; every provider that declares credentials needs its key in the table (checked by `tests/services/channels/test_credential_hot_register.py`) | ✅ |
| `pairing/` | Subpackage | Model-agnostic channel token binding & visual pairing wizard | ✅ |

## Dependencies

- `dependency_install.py` → `myrm_agent_harness.runtime.deps.lazy_deps`, `app.channels.providers.registry`
- Optional capability extras (e.g. WeChat voice `platform.wechat-silk`) install via explicit Settings action; WARNING issues do not block channel enable.
- `sdk_registration.py` → `app.channels.core.factory`, `app.core.channel_bridge`
- `credential_reload.py` → `app.channels.providers.registry`, `app.channels.core.credentials`, `app.core.channel_bridge`
- `api/channels/router.py` → both modules above
- `api/config/router.py`, `api/config/telegram_onboarding.py`, `api/channels/instances_credentials.py` and `api/channels/feishu_register.py` → `credential_reload.py`
