"""External source migration domain: discovery, manifest SSOT, payload loading, splitting.

[INPUT]
- Wizard discovery payload: ``{competitor, root, files}`` (from ``api.migration.discovery``).
- ZIP upload payloads: ChatGPT ``conversations.json`` / gbrain Markdown files.
- Hermes ``.env`` (secrets opt-in), Hermes ``config.json`` (model/auxiliary config).

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``source`` subpackage:
  - source_discovery: DiscoveredFile / ExternalSource / DiscoveryResult + discover_external_sources
  - source_manifest: migration source SSOT (display name, import map, discover/deep-link modes)
  - source_probes: per-source filesystem probes (hermes/claude/openclaw/codex/pi)
  - source_payload_loader: load_source_payload / build_coverage_items / extract_pending_skills
  - source_payload_loaders_impl: base loaders (hermes/codex/claude/chatgpt/gbrain)
  - source_payload_split: instruction plan + memory payload extraction
  - source_migration_types: four-lane migration DTOs
  - source_secrets_importer: opt-in API-key import from competitor .env files
  - source_model_migrator: competitor model config → Myrm model settings

[POS]
Server business layer. Single migration-source domain: every ``source_*`` module
lives here so the closed source set (5 wizard-discovered + 2 ZIP-only) stays
co-located with its loaders, probes and DTOs and can never drift apart.
"""

from app.services.migration.source.source_discovery import (
    ConfidenceLevel,
    DiscoveredFile,
    DiscoveryResult,
    ExternalSource,
    discover_external_sources,
)
from app.services.migration.source.source_manifest import (
    MigrationImportSource,
    MigrationSourceManifestEntry,
    MigrationSourceManifestPayloadItem,
    migration_source_deep_link_ids,
    migration_source_display_name,
    migration_source_import_map,
    migration_source_local_scan_ids,
    migration_source_manifest_authoritative,
    migration_source_manifest_authoritative_for_ids,
    migration_source_manifest_entries,
    migration_source_manifest_ids,
    migration_source_manifest_payload,
)
from app.services.migration.source.source_migration_types import (
    InstructionApplyResult,
    InstructionRollbackRecord,
    MigrationLanePreview,
    MigrationWizardOptions,
    SourceInstructionPlan,
    WorkspaceRuleWrite,
    build_lane_previews,
    instruction_char_total,
)
from app.services.migration.source.source_model_migrator import (
    AuxiliaryMigrationResult,
    extract_hermes_auxiliary_config,
    migrate_hermes_auxiliary_models,
    migrate_openclaw_default_model,
)
from app.services.migration.source.source_payload_loader import (
    SourceDiscoveryPayload,
    build_coverage_items,
    extract_pending_skills,
    is_source_discovery_payload,
    load_source_payload,
    supported_source_ids,
)
from app.services.migration.source.source_payload_loaders_impl import (
    load_chatgpt,
    load_claude,
    load_codex,
    load_gbrain,
    load_hermes,
    load_openclaw,
    load_pi,
)
from app.services.migration.source.source_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
    has_api_keys,
)
from app.services.migration.source.source_probes import (
    discover_claude,
    discover_codex,
    discover_hermes,
    discover_openclaw,
    discover_pi,
)
from app.services.migration.source.source_secrets_importer import (
    external_source_providers_configured,
    import_external_source_secrets,
)

__all__ = [
    "AuxiliaryMigrationResult",
    "ConfidenceLevel",
    "DiscoveredFile",
    "DiscoveryResult",
    "ExternalSource",
    "InstructionApplyResult",
    "InstructionRollbackRecord",
    "MigrationImportSource",
    "MigrationLanePreview",
    "MigrationSourceManifestEntry",
    "MigrationSourceManifestPayloadItem",
    "MigrationWizardOptions",
    "SourceDiscoveryPayload",
    "SourceInstructionPlan",
    "WorkspaceRuleWrite",
    "build_coverage_items",
    "build_instruction_plan",
    "build_lane_previews",
    "discover_claude",
    "discover_codex",
    "discover_external_sources",
    "discover_hermes",
    "discover_openclaw",
    "discover_pi",
    "extract_hermes_auxiliary_config",
    "extract_memory_payload",
    "extract_pending_skills",
    "external_source_providers_configured",
    "has_api_keys",
    "import_external_source_secrets",
    "instruction_char_total",
    "is_source_discovery_payload",
    "load_chatgpt",
    "load_claude",
    "load_codex",
    "load_gbrain",
    "load_hermes",
    "load_openclaw",
    "load_pi",
    "load_source_payload",
    "migrate_hermes_auxiliary_models",
    "migrate_openclaw_default_model",
    "migration_source_deep_link_ids",
    "migration_source_display_name",
    "migration_source_import_map",
    "migration_source_local_scan_ids",
    "migration_source_manifest_authoritative",
    "migration_source_manifest_authoritative_for_ids",
    "migration_source_manifest_entries",
    "migration_source_manifest_ids",
    "migration_source_manifest_payload",
    "supported_source_ids",
]
