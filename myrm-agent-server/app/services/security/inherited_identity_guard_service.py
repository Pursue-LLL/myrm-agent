"""Service layer for Inherited Identity Protection and Session Resume Guard.

[INPUT]
- SanitizeEnvRequest, ResolveSessionRefRequest, CreateResumePlanRequest DTOs.

[OUTPUT]
- SanitizeEnvResponse, ResolveSessionRefResponse, CreateResumePlanResponse DTOs.

[POS]
- Server service encapsulating Herdr #4461 clear inherited terminal and agent session identity.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.inherited_identity_guard import (
    DEFAULT_DENIED_ENV_KEYS,
    AgentResumePlan,
    AgentSessionRef,
    AgentSessionRefKind,
    InheritedIdentitySanitizer,
    SanitizationPolicy,
    SanitizationResult,
    is_official_agent_source,
    validate_resume_argv,
)

from app.schemas.inherited_identity_guard import (
    AgentResumePlanDto,
    AgentSessionRefDto,
    CreateResumePlanRequest,
    CreateResumePlanResponse,
    ResolveSessionRefRequest,
    ResolveSessionRefResponse,
    SanitizeEnvRequest,
    SanitizeEnvResponse,
    SessionRefKindDto,
)

logger = logging.getLogger(__name__)


class InheritedIdentityGuardService:
    """Service providing terminal identity sanitization and official session resume validation."""

    def __init__(self, sanitizer: InheritedIdentitySanitizer | None = None) -> None:
        self._sanitizer = sanitizer or InheritedIdentitySanitizer()

    def sanitize_environment(self, request: SanitizeEnvRequest) -> SanitizeEnvResponse:
        """Sanitize environment variables by stripping inherited terminal and agent session identifiers."""
        denied_keys = set(DEFAULT_DENIED_ENV_KEYS)
        if request.extra_removals:
            denied_keys.update(request.extra_removals)

        custom_policy = SanitizationPolicy(
            denied_env_keys=frozenset(denied_keys),
            allow_system_only=request.allow_system_only,
        )
        sanitizer = InheritedIdentitySanitizer(default_policy=custom_policy)

        result: SanitizationResult = sanitizer.sanitize_env(
            dirty_env=request.dirty_env,
            extra=request.extra_overrides,
        )

        logger.info(
            "Sanitized environment: %d variables purged, isolated=%s",
            result.purged_count,
            result.is_isolated,
        )

        return SanitizeEnvResponse(
            sanitized_env=result.sanitized_env,
            purged_keys=result.purged_keys,
            purged_count=result.purged_count,
            is_isolated=result.is_isolated,
        )

    def resolve_session_reference(
        self, request: ResolveSessionRefRequest
    ) -> ResolveSessionRefResponse:
        """Resolve and validate an agent session reference against official origins."""
        if not is_official_agent_source(request.source, request.agent):
            logger.warning(
                "Rejected unofficial agent source pair: (%s, %s)",
                request.source,
                request.agent,
            )
            return ResolveSessionRefResponse(
                resolved=False,
                reason=f"Source '{request.source}' is not an official authorized source for agent '{request.agent}'",
            )

        ref: AgentSessionRef | None = self._sanitizer.resolve_session_ref(
            source=request.source,
            agent=request.agent,
            session_id=request.session_id,
            session_path=request.session_path,
        )

        if ref is None:
            return ResolveSessionRefResponse(
                resolved=False,
                reason="Invalid session identifier, path, or unsupported reference kind for agent",
            )

        kind_dto = SessionRefKindDto.ID if ref.kind == AgentSessionRefKind.ID else SessionRefKindDto.PATH
        return ResolveSessionRefResponse(
            resolved=True,
            session_ref=AgentSessionRefDto(kind=kind_dto, value=ref.value),
        )

    def generate_resume_plan(
        self, request: CreateResumePlanRequest
    ) -> CreateResumePlanResponse:
        """Derive and validate an official agent resume plan."""
        if not is_official_agent_source(request.source, request.agent):
            return CreateResumePlanResponse(
                is_valid=False,
                reason=f"Source '{request.source}' is not an official authorized source for agent '{request.agent}'",
            )

        kind = (
            AgentSessionRefKind.ID
            if request.session_ref.kind == SessionRefKindDto.ID
            else AgentSessionRefKind.PATH
        )
        harness_ref = AgentSessionRef(kind=kind, value=request.session_ref.value)

        resolved_argv = self._sanitizer.resolve_argv(
            agent=request.agent,
            session_ref=harness_ref,
            is_windows=request.is_windows,
        )
        if resolved_argv is None:
            return CreateResumePlanResponse(
                is_valid=False,
                reason=f"Agent '{request.agent}' does not support session ref kind '{request.session_ref.kind.value}'",
            )

        valid_argv, argv_err = validate_resume_argv(resolved_argv)
        if not valid_argv:
            return CreateResumePlanResponse(
                is_valid=False,
                reason=argv_err,
            )

        plan: AgentResumePlan | None = self._sanitizer.create_resume_plan(
            source=request.source,
            agent=request.agent,
            session_ref=harness_ref,
            cwd=request.cwd,
            is_windows=request.is_windows,
        )

        if plan is None:
            return CreateResumePlanResponse(
                is_valid=False,
                reason="Failed to construct resume plan",
            )

        return CreateResumePlanResponse(
            is_valid=True,
            plan=AgentResumePlanDto(
                agent=plan.agent,
                argv=plan.argv,
                dedupe_key=plan.dedupe_key,
            ),
        )


inherited_identity_guard_service = InheritedIdentityGuardService()
