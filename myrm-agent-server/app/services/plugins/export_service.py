"""Expert export facade (business layer).

Turns one expert and everything it depends on into an Agent Plugins 1.0.0 package
that another installation can import: sub-experts, custom skills (with a
secret-redaction review), preset skills by name, connector declarations with secret
placeholders, and workspace templates. What cannot travel is reported, never dropped
silently. The package is verified by parsing it back before it is handed out.

[INPUT]
- ._export_closure::build_export_plan (POS: dependency closure of the expert.)
- ._export_render::corpus_of, spec_of (POS: reviewable corpus and package spec.)
- app.core.skills.packaging.redaction::redact_files, review_digest (POS: the single redaction pass shared with skill export.)
- myrm_agent_harness.agent.plugins::build_plugin_bundle (POS: deterministic, self-verified package writer.)

[OUTPUT]
- ExportPreview / preview_expert_export: what an export would contain and which findings need a decision.
- ExportedPackage / export_expert: the verified package bytes.
- ExportError / ExportErrorCode / Omit / OmittedItem / OmittedKind / ExportPlan / secret_names_of: re-exported contract types and helpers.

[POS]
Export orchestration. Collecting lives in ``_export_closure``, rendering in ``_export_render``,
the HTTP contract in ``app.api.plugins.export``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from myrm_agent_harness.agent.plugins import build_plugin_bundle
from myrm_agent_harness.agent.skills.security.content_sanitizer import Redaction

from app.core.skills.packaging.redaction import redact_files
from app.core.skills.packaging.redaction import review_digest as compute_review_digest

from ._export_closure import build_export_plan
from ._export_connector import secret_names_of
from ._export_models import ExportError, ExportErrorCode, ExportPlan, Omit, OmittedItem, OmittedKind
from ._export_render import PACKAGE_VERSION, corpus_of, spec_of

__all__ = [
    "ExportError",
    "ExportErrorCode",
    "ExportPlan",
    "ExportPreview",
    "ExportedPackage",
    "Omit",
    "OmittedItem",
    "OmittedKind",
    "export_expert",
    "preview_expert_export",
    "secret_names_of",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportPreview:
    plan: ExportPlan
    version: str
    redactions: dict[str, list[Redaction]]  # findings per reviewed path (indices are what a decision refers to)
    review_digest: str  # fingerprint of the reviewed texts; decisions are only valid for them
    package_bytes: int | None  # size of the package a dry run produced
    build_error: str | None  # why the dry run failed (the export would fail the same way)


@dataclass(frozen=True)
class ExportedPackage:
    zip_content: bytes
    filename: str


async def preview_expert_export(agent_id: str) -> ExportPreview:
    """Collect the closure, scan it and dry-run the package build."""
    plan = await build_export_plan(agent_id)
    corpus = corpus_of(plan)
    # Scanning and zipping are CPU-bound; keep them off the event loop.
    outcome = await asyncio.to_thread(redact_files, corpus, apply=False)
    built = await asyncio.to_thread(build_plugin_bundle, spec_of(plan, corpus))
    return ExportPreview(
        plan=plan,
        version=PACKAGE_VERSION,
        redactions=outcome.redactions,
        review_digest=compute_review_digest(corpus),
        package_bytes=len(built.zip_content) if built.success and built.zip_content else None,
        build_error=None if built.success else built.error,
    )


async def export_expert(
    agent_id: str,
    *,
    apply_redactions: bool,
    ignored_redactions: Mapping[str, Sequence[int]] | None,
    review_digest: str | None,
) -> ExportedPackage:
    """Build the package. Every finding must be redacted (``apply_redactions``) or explicitly kept."""
    plan = await build_export_plan(agent_id)
    corpus = corpus_of(plan)

    keeps_findings = any(ignored_redactions.values()) if ignored_redactions else False
    if keeps_findings and review_digest != compute_review_digest(corpus):
        raise ExportError(
            ExportErrorCode.CHANGED_SINCE_PREVIEW,
            "The expert changed since the redaction preview; review the findings again.",
        )

    outcome = await asyncio.to_thread(redact_files, corpus, apply=apply_redactions, ignored=ignored_redactions)
    if outcome.redactions and not apply_redactions:
        raise ExportError(
            ExportErrorCode.REVIEW_REQUIRED,
            "Findings remain that were neither redacted nor kept; review them before exporting.",
        )

    built = await asyncio.to_thread(build_plugin_bundle, spec_of(plan, outcome.files))
    if not built.success or built.zip_content is None or built.filename is None:
        logger.warning("Expert export rejected for %s: %s", agent_id, built.error)
        raise ExportError(ExportErrorCode.PACKAGE_REJECTED, built.error or "The package could not be built")
    return ExportedPackage(zip_content=built.zip_content, filename=built.filename)
