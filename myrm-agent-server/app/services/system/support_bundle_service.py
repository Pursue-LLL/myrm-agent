"""Technical Support Debug Bundle Service.

[INPUT]
- app.config.settings::get_settings (POS: System paths & deploy mode)
- app.core.infra.health.health_snapshot::collect_health_snapshot (POS: Doctor health probes)
- app.core.infra.health.health_presenter::present_health_report (POS: Deploy-aware Doctor report fields)
- app.services.agent.agent_service::AgentService (POS: Business agent list)
- myrm_agent_harness.api::redact_sensitive_text (POS: Harness-level credential redaction)
- myrm_agent_harness.observability.diagnostics.protocols::redact_health_report (POS: Diagnostic report sanitization)

[OUTPUT]
- SupportBundleService.build_bundle_zip: Assemble the in-memory redacted zip archive.

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

_COLLECTION_TIMEOUT_SECONDS = 30.0  # the Doctor probes take up to ~8 s on a cold start
_MAX_PROFILES = 50
_MAX_EVENT_LOG_FILES = 10
_MAX_BYTES_PER_EVENT_LOG = 64 * 1024  # 64 KB per session trace sample
_TRACE_OMITTED_NOTICE = "[trace omitted: the newest event is larger than the per-file size limit]\n"


def _safe_json_dumps(data: object) -> str:
    """Serialize object to formatted JSON string, applying sensitive text redaction."""
    raw_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return redact_sensitive_text(raw_str)


def _tail_complete_lines(text: str, max_bytes: int) -> str:
    """Newest whole lines of ``text`` that fit in ``max_bytes`` of UTF-8.

    A window that starts mid-line would carry the tail of a credential without the key name or
    prefix the redactor needs to recognise it, so the partial first line is dropped.
    """
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    cut = len(raw) - max_bytes
    window = raw[cut:]
    if raw[cut - 1 : cut] != b"\n":
        _, newline, window = window.partition(b"\n")
        if not newline:
            return ""
    return window.decode("utf-8", errors="replace")


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
            "checkpointer_mode": settings.database.checkpointer_mode or "sqlite",
            "graph_store": "age" if settings.database.database_url else "sqlite",
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
                    "harness": harness_reports,
                    "server": server_reports,
                }
        except Exception as exc:
            logger.warning("Failed to capture doctor health snapshot: %s", exc)
            return {"error": f"Doctor probe timeout or failure: {exc}"}

    @classmethod
    async def collect_agent_profiles(cls) -> list[dict[str, object]]:
        """Collect agent configuration metadata; prompts, memory policy and per-skill settings are never read."""
        try:
            profiles, _total = await AgentService.get_agent_list(page=1, page_size=_MAX_PROFILES)
            return [
                {
                    "id": p.id,
                    "display_name": p.display_name,
                    "model": p.model,
                    "max_iterations": p.max_iterations,
                    "built_in": p.built_in,
                    "no_builtin_tools": p.no_builtin_tools,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "tools_allowed": list(p.tools_allowed or []),
                    "skills_count": len(p.skills or []),
                }
                for p in profiles
            ]
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
                    tail = _tail_complete_lines(raw_content, _MAX_BYTES_PER_EVENT_LOG)
                    if raw_content and not tail:
                        tail = _TRACE_OMITTED_NOTICE
                    traces[file_path.name] = redact_sensitive_text(tail)
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

        return zip_buffer.getvalue()
