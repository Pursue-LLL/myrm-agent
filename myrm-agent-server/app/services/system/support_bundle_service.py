"""Technical Support Debug Bundle Service.

[INPUT]
- app.config.settings::get_settings (POS: System paths & deploy mode)
- app.core.infra.health.health_snapshot::collect_health_snapshot (POS: Doctor health probes)
- app.services.agent.profile.profile_resolver::get_agent_profile_resolver (POS: Active agent profile data)
- myrm_agent_harness.core.security.redact::redact_sensitive_text (POS: Harness-level credential redaction)
- myrm_agent_harness.observability.diagnostics.protocols::redact_health_report (POS: Diagnostic report sanitization)

[OUTPUT]
- generate_support_debug_bundle_bytes: Assemble in-memory redacted zip archive.

[POS]
Generates a structured, self-contained, and deeply redacted diagnostic ZIP package
for developer support, issue reporting, and cluster health auditing.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import platform
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from myrm_agent_harness.api import redact_sensitive_text
from myrm_agent_harness.observability.diagnostics.protocols import redact_health_report

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import get_settings
from app.core.infra.health.health_presenter import present_health_report
from app.core.infra.health.health_snapshot import collect_health_snapshot
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

_MAX_BUNDLE_BYTES = 10 * 1024 * 1024  # 10 MB ceiling
_COLLECTION_TIMEOUT_SECONDS = 5.0
_MAX_EVENT_LOG_FILES = 10
_MAX_BYTES_PER_EVENT_LOG = 64 * 1024  # 64 KB per session trace sample


def _safe_json_dumps(data: object) -> str:
    """Serialize object to formatted JSON string, applying sensitive text redaction."""
    raw_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return redact_sensitive_text(raw_str)


class SupportBundleService:
    """Orchestrates system diagnostics, profile metadata, and trace redaction into a zip bundle."""

    @classmethod
    async def collect_system_info(cls) -> dict[str, object]:
        """Gather host environment, runtime versions, and storage metrics."""
        settings = get_settings()
        state_dir = Path(settings.database.state_dir)
        try:
            usage = shutil.disk_usage(state_dir if state_dir.exists() else state_dir.parent)
            disk_info = {
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            }
        except OSError:
            disk_info = {"error": "Failed to read disk usage"}

        return {
            "platform": platform.platform(),
            "python_version": sys.version,
            "os_name": os.name,
            "deploy_mode": get_deploy_mode().value,
            "database_type": settings.database.engine,
            "qdrant_mode": settings.qdrant.mode if hasattr(settings, "qdrant") else "embedded",
            "disk_metrics": disk_info,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    async def collect_doctor_diagnostics(cls) -> dict[str, object]:
        """Collect full Doctor component reports with Harness + Server redaction."""
        try:
            async with asyncio.timeout(_COLLECTION_TIMEOUT_SECONDS):
                snapshot = await collect_health_snapshot()
                harness_reports = [redact_health_report(present_health_report(r)).model_dump() for r in snapshot.harness_reports]
                server_reports = [redact_health_report(present_health_report(r)).model_dump() for r in snapshot.server_reports]
                return {
                    "is_healthy": snapshot.is_healthy,
                    "harness": harness_reports,
                    "server": server_reports,
                }
        except Exception as exc:
            logger.warning("Failed to capture doctor health snapshot: %s", exc)
            return {"error": f"Doctor probe timeout or failure: {exc}"}

    @classmethod
    async def collect_agent_profiles(cls) -> list[dict[str, object]]:
        """Collect sanitized Agent Profiles (masking prompts, tokens, and private secrets)."""
        try:
            profiles = await AgentService.list_profiles(limit=50)
            results: list[dict[str, object]] = []
            for p in profiles:
                results.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "model": p.model,
                        "is_active": p.is_active,
                        "max_iterations": p.max_iterations,
                        "prompt_mode": getattr(p, "prompt_mode", "general"),
                        "created_at": p.created_at.isoformat() if p.created_at else None,
                        "enabled_builtin_tools": list(p.enabled_builtin_tools) if p.enabled_builtin_tools else [],
                        "skills_count": len(p.skills) if hasattr(p, "skills") and p.skills else 0,
                        "mcp_servers_count": len(p.mcp_servers) if hasattr(p, "mcp_servers") and p.mcp_servers else 0,
                    }
                )
            return results
        except Exception as exc:
            logger.warning("Failed to collect agent profiles: %s", exc)
            return [{"error": f"Failed to list profiles: {exc}"}]

    @classmethod
    def collect_recent_event_traces(cls) -> dict[str, str]:
        """Read and redact recent event log trace slices."""
        settings = get_settings()
        event_log_dir = Path(settings.database.event_log_dir)
        if not event_log_dir.exists() or not event_log_dir.is_dir():
            return {}

        traces: dict[str, str] = {}
        try:
            files = sorted(
                event_log_dir.glob("*.jsonl"),
                key=lambda f: f.stat().st_mtime,
                reverse=True,
            )[:_MAX_EVENT_LOG_FILES]

            for file_path in files:
                try:
                    raw_content = file_path.read_text(encoding="utf-8", errors="replace")
                    if len(raw_content) > _MAX_BYTES_PER_EVENT_LOG:
                        raw_content = raw_content[-_MAX_BYTES_PER_EVENT_LOG:]
                    sanitized_content = redact_sensitive_text(raw_content)
                    traces[file_path.name] = sanitized_content
                except OSError as err:
                    traces[file_path.name] = f"[Read error: {err}]"
        except Exception as exc:
            logger.warning("Failed to scan event logs: %s", exc)

        return traces

    @classmethod
    async def build_bundle_zip(
        cls,
        *,
        include_traces: bool = True,
        include_profiles: bool = True,
    ) -> bytes:
        """Assemble all diagnostic components into an in-memory zip file."""
        system_info = await cls.collect_system_info()
        doctor_report = await cls.collect_doctor_diagnostics()
        profiles = await cls.collect_agent_profiles() if include_profiles else []
        traces = cls.collect_recent_event_traces() if include_traces else {}

        manifest = {
            "bundle_version": "1.0.0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "generator": "Myrm SupportBundleService",
            "includes": {
                "system_info": True,
                "doctor_diagnostics": True,
                "agent_profiles": include_profiles,
                "event_traces_count": len(traces),
            },
        }

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("MANIFEST.json", _safe_json_dumps(manifest))
            zf.writestr("system_info.json", _safe_json_dumps(system_info))
            zf.writestr("doctor_health.json", _safe_json_dumps(doctor_report))
            if include_profiles:
                zf.writestr("active_profiles.json", _safe_json_dumps(profiles))
            if include_traces and traces:
                for filename, trace_content in traces.items():
                    zf.writestr(f"traces/{filename}", trace_content)

        zip_bytes = zip_buffer.getvalue()
        if len(zip_bytes) > _MAX_BUNDLE_BYTES:
            logger.warning("Support bundle exceeded max size %d, truncating traces", _MAX_BUNDLE_BYTES)
            # Rebuild without traces if over budget
            return await cls.build_bundle_zip(include_traces=False, include_profiles=include_profiles)

        return zip_bytes
