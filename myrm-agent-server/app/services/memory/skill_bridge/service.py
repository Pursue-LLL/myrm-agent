"""Business service coordinating external agent memory skill installation and query gateway.

[POS]
app/services/memory/skill_bridge/service.py
Provides discovery of agent targets on the host machine, idempotent marker installation/uninstallation,
sub-20ms local memory queries, and security-hardened fact contributions.

[INPUT]
- app.schemas.external_skill_bridge DTOs
- myrm_agent_harness.toolkits.memory facade

[OUTPUT]
- ExternalAgentSkillBridgeService, get_external_skill_bridge_service
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    START_MARKER,
    ExternalAgentSkillWriter,
    ExternalAgentTargetRegistry,
    ExternalAgentType,
    LocalSecretRedactor,
    MemoryPluginConflictDetector,
    ShannonEntropyInspector,
    SkillInstallConfig,
)

from app.schemas.external_skill_bridge import (
    ExternalAgentTargetDTO,
    ExternalMemoryContributeRequest,
    ExternalMemoryContributeResponse,
    ExternalMemoryHitDTO,
    ExternalMemoryQueryRequest,
    ExternalMemoryQueryResponse,
    ExternalTargetsListResponse,
    InstallSkillBridgeRequest,
    InstallSkillBridgeResponse,
    UninstallSkillBridgeRequest,
    UninstallSkillBridgeResponse,
)

AGENT_DISPLAY_NAMES: dict[ExternalAgentType, str] = {
    ExternalAgentType.CURSOR: "Cursor IDE (.cursorrules / mdc)",
    ExternalAgentType.CLAUDE_CODE: "Anthropic Claude Code (CLAUDE.md)",
    ExternalAgentType.CODEX: "Codex Environment (CODEX.md)",
    ExternalAgentType.HERMES: "Hermes Agent (HERMES.md)",
    ExternalAgentType.OPENCLAW: "OpenClaw Autonomous Agent (OPENCLAW.md)",
}


class ExternalAgentSkillBridgeService:
    """Service managing external agent skill bridge integrations and local memory gateway."""

    def __init__(
        self,
        registry: ExternalAgentTargetRegistry | None = None,
        skill_writer: ExternalAgentSkillWriter | None = None,
    ) -> None:
        self._registry = registry or ExternalAgentTargetRegistry()
        self._writer = skill_writer or ExternalAgentSkillWriter(registry=self._registry)
        self._redactor = LocalSecretRedactor(enable_entropy=False)
        self._entropy_inspector = ShannonEntropyInspector(entropy_threshold=4.5, min_token_len=24)
        self._contributed_facts: dict[str, dict[str, str]] = {}
        self._seed_default_facts()

    def _seed_default_facts(self) -> None:
        """Seed foundational architectural preferences."""
        defaults = [
            (
                "preference",
                "Strict typing is enforced across all repositories: zero Any types allowed.",
            ),
            (
                "architecture",
                "Single-file limit is 400 lines maximum; all modules must maintain single responsibility.",
            ),
            (
                "protocol",
                "All Python source files require 3-line fractal headers: [POS], [INPUT], [OUTPUT].",
            ),
        ]
        for category, text in defaults:
            fact_id = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
            self._contributed_facts[fact_id] = {
                "id": fact_id,
                "text": text,
                "category": category,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

    def list_supported_targets(
        self,
        workspace_root: str | None = None,
        global_config: bool = False,
    ) -> ExternalTargetsListResponse:
        """Scan host and return configured status for all supported agent types."""
        root = Path(workspace_root) if workspace_root else None
        targets_dto: list[ExternalAgentTargetDTO] = []

        for agent_type in self._registry.list_supported_agents():
            adapter = self._registry.get(agent_type)
            target_path = adapter.get_default_target_path(
                workspace_root=root,
                global_config=global_config,
            )

            is_installed = False
            has_conflict = False
            conflicts: list[str] = []

            if target_path.exists() and target_path.is_file():
                try:
                    content = target_path.read_text(encoding="utf-8", errors="replace")
                    is_installed = START_MARKER in content
                    conflict_report = MemoryPluginConflictDetector.inspect_content(content)
                    has_conflict = conflict_report.has_conflict
                    conflicts = conflict_report.conflicting_rules
                except OSError:
                    pass

            display_name = AGENT_DISPLAY_NAMES.get(agent_type, agent_type.value)
            targets_dto.append(
                ExternalAgentTargetDTO(
                    agent_type=agent_type.value,
                    name=display_name,
                    target_path=str(target_path),
                    is_installed=is_installed,
                    has_conflict=has_conflict,
                    conflicts=conflicts,
                    is_read_only=False,
                )
            )

        return ExternalTargetsListResponse(
            targets=targets_dto,
            total_supported=len(targets_dto),
        )

    def install_bridge(self, request: InstallSkillBridgeRequest) -> InstallSkillBridgeResponse:
        """Install or update bridge instructions into specified target configuration."""
        try:
            agent_enum = ExternalAgentType(request.agent_type)
        except ValueError:
            return InstallSkillBridgeResponse(
                agent_type=request.agent_type,
                target_path="",
                action="failed",
                success=False,
                details="",
                error=f"Unsupported agent type: {request.agent_type}",
            )

        config = SkillInstallConfig(
            agent_type=agent_enum,
            workspace_root=Path(request.workspace_root) if request.workspace_root else None,
            global_config=request.global_config,
            api_base_url=request.api_base_url,
            custom_target_path=Path(request.custom_target_path) if request.custom_target_path else None,
            read_only=request.read_only,
            max_recalled_facts=request.max_recalled_facts,
        )

        res = self._writer.install(config)
        return InstallSkillBridgeResponse(
            agent_type=res.agent_type.value,
            target_path=str(res.target_path),
            action=res.action.value,
            success=res.success,
            details=res.details,
            error=res.error,
        )

    def uninstall_bridge(self, request: UninstallSkillBridgeRequest) -> UninstallSkillBridgeResponse:
        """Uninstall bridge instructions from specified target configuration."""
        try:
            agent_enum = ExternalAgentType(request.agent_type)
        except ValueError:
            return UninstallSkillBridgeResponse(
                agent_type=request.agent_type,
                target_path="",
                removed=False,
                file_deleted=False,
                success=False,
                details="",
                error=f"Unsupported agent type: {request.agent_type}",
            )

        config = SkillInstallConfig(
            agent_type=agent_enum,
            workspace_root=Path(request.workspace_root) if request.workspace_root else None,
            global_config=request.global_config,
            custom_target_path=Path(request.custom_target_path) if request.custom_target_path else None,
        )

        res = self._writer.uninstall(config)
        return UninstallSkillBridgeResponse(
            agent_type=res.agent_type.value,
            target_path=str(res.target_path),
            removed=res.removed,
            file_deleted=res.file_deleted,
            success=res.success,
            details=res.details,
            error=res.error,
        )

    def query_external_memory(self, request: ExternalMemoryQueryRequest) -> ExternalMemoryQueryResponse:
        """Execute fast, low-latency recall for external coding tools (<20ms)."""
        start_time = time.perf_counter()
        query_lower = request.query.lower().strip()
        matching_hits: list[ExternalMemoryHitDTO] = []

        tokens = [t for t in query_lower.split() if len(t) > 1]

        for item in self._contributed_facts.values():
            if request.category and item["category"] != request.category:
                continue

            text_lower = item["text"].lower()
            score = 0.5
            if query_lower in text_lower:
                score = 1.0
            elif tokens and any(tok in text_lower for tok in tokens):
                score = 0.8

            if score >= 0.6 or not tokens:
                matching_hits.append(
                    ExternalMemoryHitDTO(
                        id=item["id"],
                        text=item["text"],
                        category=item["category"],
                        score=score,
                        created_at=item["created_at"],
                    )
                )

        matching_hits.sort(key=lambda x: x.score, reverse=True)
        bounded_hits = matching_hits[: request.limit]
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return ExternalMemoryQueryResponse(
            hits=bounded_hits,
            total_hits=len(bounded_hits),
            took_ms=round(elapsed_ms, 2),
        )

    def contribute_external_memory(
        self, request: ExternalMemoryContributeRequest
    ) -> ExternalMemoryContributeResponse:
        """Sanitize and safely accept new memory facts contributed by external agents."""
        text = request.text.strip()

        # Step 1: Redact known credentials & patterns
        redacted, _ = self._redactor.scrub(text)

        # Step 2: Reject unmasked high-entropy raw secret payloads
        high_entropy_hits = self._entropy_inspector.inspect_text(redacted)
        if high_entropy_hits:
            return ExternalMemoryContributeResponse(
                accepted=False,
                redacted_text="",
                reason="Security violation: High-entropy raw secret or credential detected.",
            )

        # Step 3: Compute deterministic fingerprint
        fact_id = hashlib.sha256(redacted.encode("utf-8")).hexdigest()[:12]
        self._contributed_facts[fact_id] = {
            "id": fact_id,
            "text": redacted,
            "category": request.category,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return ExternalMemoryContributeResponse(
            accepted=True,
            fact_id=fact_id,
            redacted_text=redacted,
            reason=None,
        )


_service_instance: ExternalAgentSkillBridgeService | None = None


def get_external_skill_bridge_service() -> ExternalAgentSkillBridgeService:
    """Dependency injection provider returning singleton service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ExternalAgentSkillBridgeService()
    return _service_instance
