"""Service layer for Scoped CSS Isolation and Parallel Micro-Agent Boundary Sentinel.

[INPUT]
Logging, re, security schemas.

[OUTPUT]
ScopedCssSentinelService, get_scoped_css_sentinel_service.

[POS]
Service layer enforcing shadow DOM CSS scoping rules, blocking global CSS bleed and cross-agent DOM poisoning.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.scoped_css_sentinel import (
    ConcurrentStyleConflictDetector,
    ConcurrentStylePatch,
    ConflictCheckResult,
    CssScopingResult,
    ScopedCssAstRewriter,
)

from app.schemas.scoped_css_sentinel import (
    CheckConflictRequest,
    CheckConflictResponse,
    GlobalSelectorViolationResponse,
    ScopeCssRequest,
    ScopeCssResponse,
)

logger = logging.getLogger(__name__)


class ScopedCssSentinelService:
    """Coordinates AST-level CSS scoping and multi-agent concurrent style collision detection."""

    def __init__(
        self,
        rewriter: ScopedCssAstRewriter | None = None,
        detector: ConcurrentStyleConflictDetector | None = None,
    ) -> None:
        self.rewriter = rewriter or ScopedCssAstRewriter()
        self.detector = detector or ConcurrentStyleConflictDetector(rewriter=self.rewriter)

    def scope_css(self, req: ScopeCssRequest) -> ScopeCssResponse:
        """Enforce component scoping and bar global root selectors."""
        res = self.rewriter.scope_css(req.css_content, req.scope_id)
        if not res.is_valid:
            logger.warning(
                "Scoped CSS invariant violation detected for scope '%s': %d violations",
                res.scope_id,
                len(res.violations),
            )
        return self._convert_scoping_result(res)

    def check_conflicts(self, req: CheckConflictRequest) -> CheckConflictResponse:
        """Validate a batch of concurrent micro-agent patches for target collisions."""
        patches = [
            ConcurrentStylePatch(
                agent_id=p.agent_id,
                component_target_id=p.component_target_id,
                css_content=p.css_content,
            )
            for p in req.patches
        ]
        result = self.detector.check_and_merge_patches(patches)
        if result.has_conflict:
            logger.warning(
                "Concurrent style patch collision detected for agents: %s. Reason: %s",
                ", ".join(result.conflicting_agents),
                result.reason,
            )
        return self._convert_conflict_result(result)

    @staticmethod
    def _convert_scoping_result(res: CssScopingResult) -> ScopeCssResponse:
        violations = [
            GlobalSelectorViolationResponse(
                selector=v.selector,
                reason=v.reason,
                severity=v.severity.value,
                line_number=v.line_number,
            )
            for v in res.violations
        ]
        return ScopeCssResponse(
            is_valid=res.is_valid,
            original_css=res.original_css,
            scoped_css=res.scoped_css,
            scope_id=res.scope_id,
            violations=violations,
            rules_rewritten=res.rules_rewritten,
        )

    @staticmethod
    def _convert_conflict_result(res: ConflictCheckResult) -> CheckConflictResponse:
        return CheckConflictResponse(
            has_conflict=res.has_conflict,
            conflicting_agents=res.conflicting_agents,
            reason=res.reason,
            merged_scoped_css=res.merged_scoped_css,
        )


_service_instance: ScopedCssSentinelService | None = None


def get_scoped_css_sentinel_service() -> ScopedCssSentinelService:
    """FastAPI dependency provider for ScopedCssSentinelService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ScopedCssSentinelService()
    return _service_instance


def reset_scoped_css_sentinel_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None
