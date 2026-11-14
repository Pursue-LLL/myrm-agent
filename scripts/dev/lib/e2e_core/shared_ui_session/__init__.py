"""Shared UI session contract for parallel chrome_e2e (Dev Gate SSOT).

[INPUT]
cdp_chat.support::ensure_e2e_search_cleared_in_browser (POS: E2E API/chat 消息 SSOT)
cdp_chat.support::get_e2e_api_url (POS: E2E API/chat 消息 SSOT)

[OUTPUT]
apply_shared_ui_session_contract: 四阶段 UI 会话隔离（RESET → BIND → BRIDGE → SEARCH）+ 最终 probe 失败时 CDP re-hydrate（最多 3 次）
prime_search_policy_env / resolve_search_policy_from_item: pytest marker → env SSOT
RESET_GLOBALS_KEEP_SEARCH_BLOCK_JS: empty 策略专用 RESET 变体（保留 __MYRM_E2E_BLOCK_SEARCH_SYNC__）

[POS]
Dev Gate 层共享 UI 污染隔离。每 chrome_e2e item 在 bootstrap / new-chat 后重置 window 全局状态。
empty 策略使用两态契约：同 nodeid+api 首轮强一致清理；后续重试快路径 short-circuit。

The contract is a package of layers; a layer imports only the layers before it in this order: scripts, policy, caps,
bridge, apply. This module re-exports the names that code outside the package reads. A patch reaches only the readers of
the module it is applied to, so a test patches the layer that reads the name (`e2e_core.shared_ui_session.apply.<name>`,
`e2e_core.shared_ui_session.caps.<name>`), not this module.
"""

from __future__ import annotations

from e2e_core.shared_ui_session.apply import (
    apply_shared_ui_session_contract,
    maybe_apply_shared_ui_session_contract,
    reapply_shared_ui_session_after_new_chat,
)
from e2e_core.shared_ui_session.bridge import SharedUiSessionChat
from e2e_core.shared_ui_session.policy import (
    DEFAULT_SEARCH_POLICY,
    E2E_SEARCH_POLICY_ENV,
    SearchPolicy,
    current_search_policy,
    prime_search_policy_env,
    resolve_search_policy_from_item,
)

__all__ = [
    "DEFAULT_SEARCH_POLICY",
    "E2E_SEARCH_POLICY_ENV",
    "SearchPolicy",
    "SharedUiSessionChat",
    "apply_shared_ui_session_contract",
    "current_search_policy",
    "maybe_apply_shared_ui_session_contract",
    "prime_search_policy_env",
    "reapply_shared_ui_session_after_new_chat",
    "resolve_search_policy_from_item",
]
