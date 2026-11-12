"""[INPUT]
- .common (POS: shared primitives)

[OUTPUT]
- AccessPolicyMixin

[POS]
Extension bridge mixin: domain access policy, authorized domains and warnings.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.services.extension.access_policy import (
    ExtensionAccessPolicy,
    is_blank_url,
    is_policy_valid_for_automation,
    is_tab_accessible,
    match_domain,
    normalize_domain_patterns,
)

if TYPE_CHECKING:
    pass


from .common import (
    DomainPolicyWarning,
    ExtensionTab,
    logger,
)


class AccessPolicyMixin:
    @staticmethod
    def _match_domain(domain: str, patterns: list[str]) -> bool:
        """Check if *domain* matches any pattern in *patterns*."""
        return match_domain(domain, patterns)

    def _current_access_policy(self) -> ExtensionAccessPolicy:
        return ExtensionAccessPolicy(
            allow_all_eligible_tabs=self._allow_all_eligible_tabs,
            authorized_domains=list(self._authorized_domains),
            paused_tab_ids=self._paused_tab_ids,
        )

    def _tab_is_accessible(self, tab: ExtensionTab) -> bool:
        return is_tab_accessible(
            tab_id=tab.tab_id,
            url=tab.url,
            domain=tab.domain,
            policy=self._current_access_policy(),
        )

    def _is_blank_agent_tab(self, tab: ExtensionTab) -> bool:
        """A blank page the Agent opened itself: it holds no site data and the Agent must be able to navigate it."""
        return tab.tab_id in self._agent_tab_ids and is_blank_url(tab.url)

    def _tab_is_visible_in_ui(self, tab: ExtensionTab) -> bool:
        return is_tab_accessible(
            tab_id=tab.tab_id,
            url=tab.url,
            domain=tab.domain,
            policy=self._current_access_policy(),
            respect_pause=False,
        )

    def is_access_policy_valid(self) -> bool:
        return is_policy_valid_for_automation(self._current_access_policy())

    @staticmethod
    def analyze_domain_policy_warnings(domains: list[str]) -> list[DomainPolicyWarning]:
        """Return warnings for surprising but valid domain policy inputs."""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in domains:
            item = raw.strip().lower().rstrip(".")
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)

        normalized_set = set(normalized)
        warnings: list[DomainPolicyWarning] = []
        for pattern in normalized:
            if not pattern.startswith("*."):
                continue
            root = pattern[2:]
            if not root or root in normalized_set:
                continue
            warnings.append(
                DomainPolicyWarning(
                    code="wildcard_includes_root",
                    pattern=pattern,
                    root_domain=root,
                )
            )
        return warnings

    def get_access_policy(self) -> ExtensionAccessPolicy:
        return self._current_access_policy()

    def _apply_access_policy_payload(self, msg: dict[str, object]) -> None:
        if "allow_all_eligible_tabs" in msg:
            self._allow_all_eligible_tabs = msg.get("allow_all_eligible_tabs") is True
        if "domains" in msg:
            raw_domains = msg.get("domains")
            if isinstance(raw_domains, list):
                self._authorized_domains = normalize_domain_patterns([str(item) for item in raw_domains])
        if "paused_tab_ids" in msg:
            raw_paused = msg.get("paused_tab_ids")
            if isinstance(raw_paused, list):
                paused: set[int] = set()
                for item in raw_paused:
                    if isinstance(item, int):
                        paused.add(item)
                    elif isinstance(item, str) and item.isdigit():
                        paused.add(int(item))
                self._paused_tab_ids = frozenset(paused)

    async def set_access_policy(
        self,
        *,
        allow_all_eligible_tabs: bool | None = None,
        authorized_domains: list[str] | None = None,
        paused_tab_ids: list[int] | None = None,
    ) -> ExtensionAccessPolicy:
        if allow_all_eligible_tabs is not None:
            self._allow_all_eligible_tabs = allow_all_eligible_tabs
        if authorized_domains is not None:
            self._authorized_domains = normalize_domain_patterns(authorized_domains)
        if paused_tab_ids is not None:
            self._paused_tab_ids = frozenset(paused_tab_ids)
        await self._notify_extension_access_policy()
        if self._connected:
            await self._sync_relay_tabs()
        return self._current_access_policy()

    async def _notify_extension_access_policy(self) -> None:
        if not self._connected or self._ws is None:
            return
        policy = self._current_access_policy()
        try:
            await self._ws.send_text(
                json.dumps(
                    {
                        "type": "set_access_policy",
                        "allow_all_eligible_tabs": policy.allow_all_eligible_tabs,
                        "domains": list(policy.authorized_domains),
                        "paused_tab_ids": sorted(policy.paused_tab_ids),
                    }
                )
            )
        except Exception as exc:
            logger.warning("Failed to notify extension of access policy: %s", exc)

    def get_authorized_domains(self) -> list[str]:
        """Get the list of domains the user has authorized."""
        return list(self._authorized_domains)

    async def set_authorized_domains(self, domains: list[str]) -> None:
        """Update authorized domains and notify extension."""
        await self.set_access_policy(authorized_domains=domains)
