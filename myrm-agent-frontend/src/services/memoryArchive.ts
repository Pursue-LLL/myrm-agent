/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * Typed Memory Archive export/restore and server-bound memory import request helpers.
 *
 * [POS]
 * Frontend Memory Archive and import API client. Owns typed HTTP contracts for archive restore, rollback, and import governance.
 */

import { apiRequest } from '@/lib/api';

export const MEMORY_ARCHIVE_SECTION_NAMES = ['memory', 'shared_context', 'conversation', 'replay', 'audit'] as const;
export const MEMORY_ARCHIVE_FILE_MAX_BYTES = 25 * 1024 * 1024;

export type MemoryArchiveSectionName = (typeof MEMORY_ARCHIVE_SECTION_NAMES)[number];
export type MemoryArchiveSectionStatus = 'ready' | 'empty' | 'partial' | 'unsupported';
export type MemoryArchiveFileErrorCode =
  | 'emptyFile'
  | 'tooLarge'
  | 'invalidJson'
  | 'invalidShape'
  | 'unsupportedFormat'
  | 'missingSections';

type MemoryArchiveFileErrorParam = string | number;

const MEMORY_ARCHIVE_SECTION_STATUSES = ['ready', 'empty', 'partial', 'unsupported'] as const;

export interface MemoryArchiveSection {
  name: MemoryArchiveSectionName;
  status: MemoryArchiveSectionStatus;
  item_count: number;
  warning_codes: string[];
}

export interface MemoryArchiveManifest {
  format: 'myrm_memory_archive';
  version: number;
  created_at: string;
  producer: string;
  sections: MemoryArchiveSection[];
  content_redacted: boolean;
}

export interface MemoryArchivePayload {
  manifest: MemoryArchiveManifest;
  data: Record<string, unknown>;
}

export class MemoryArchiveFileError extends Error {
  readonly code: MemoryArchiveFileErrorCode;
  readonly params: Record<string, MemoryArchiveFileErrorParam>;

  constructor(
    code: MemoryArchiveFileErrorCode,
    message: string,
    params: Record<string, MemoryArchiveFileErrorParam> = {},
  ) {
    super(message);
    this.name = 'MemoryArchiveFileError';
    this.code = code;
    this.params = params;
  }
}

export interface MemoryArchiveExportResponse {
  archive: MemoryArchivePayload;
}

export interface MemoryArchiveDryRunResult {
  manifest: MemoryArchiveManifest;
  total_items: number;
  supported_items: number;
  unsupported_items: number;
  warning_codes: string[];
}

export interface MemoryArchiveDryRunResponse {
  result: MemoryArchiveDryRunResult;
}

export type MemoryArchiveRestoreMode = 'safe_merge' | 'review_only' | 'skip';
export type MemoryArchiveRestoreStatus = 'ready' | 'warning' | 'critical';
export type MemoryArchiveRestoreItemStatus =
  | 'planned'
  | 'restored'
  | 'skipped'
  | 'conflict'
  | 'missing'
  | 'failed'
  | 'rolled_back';

export interface MemoryArchiveRestoreSectionPlan {
  section: MemoryArchiveSectionName;
  mode: MemoryArchiveRestoreMode;
  item_count: number;
  restorable_items: number;
  review_only_items: number;
  skipped_items: number;
  conflict_items: number;
  blocked_items: number;
  warning_codes: string[];
  target_kinds: string[];
}

export interface MemoryArchiveRestoreSecurityFinding {
  section: MemoryArchiveSectionName;
  item_kind: string;
  source_id: string;
  verdict: 'warn' | 'redacted' | 'blocked';
  codes: string[];
}

export interface MemoryArchiveRestorePlan {
  version: number;
  plan_hash: string;
  status: MemoryArchiveRestoreStatus;
  total_items: number;
  restorable_items: number;
  review_only_items: number;
  skipped_items: number;
  conflict_items: number;
  blocked_items: number;
  warning_codes: string[];
  sections: MemoryArchiveRestoreSectionPlan[];
  security_findings: MemoryArchiveRestoreSecurityFinding[];
}

export interface MemoryArchiveRestoreDryRunResult {
  manifest: MemoryArchiveManifest;
  plan: MemoryArchiveRestorePlan;
  payload_hash: string;
}

export interface MemoryArchiveRestoreMutationRef {
  section: MemoryArchiveSectionName;
  item_kind: string;
  source_id: string;
  target_id: string;
  status: MemoryArchiveRestoreItemStatus;
  reason: string;
}

export interface MemoryArchiveRestoreResult {
  restore_batch_id: string;
  payload_hash: string;
  plan_hash: string;
  restored: Record<string, number>;
  total_restored: number;
  skipped_items: number;
  conflict_items: number;
  failed_items: number;
  warnings: string[];
  mutation_refs: MemoryArchiveRestoreMutationRef[];
  diagnostic_status?: string | null;
  diagnostic_run_id?: string | null;
  diagnostic_failed_count?: number;
}

export interface MemoryArchiveRestoreRollbackPreview {
  restore_batch_id: string;
  total_items: number;
  reversible_items: number;
  items_by_section: Record<string, number>;
  missing_items: number;
  failed_items: number;
  warning_codes: string[];
}

export interface MemoryArchiveRestoreRollbackResult {
  restore_batch_id: string;
  rolled_back: Record<string, number>;
  total_rolled_back: number;
  missing_items: number;
  failed_items: number;
  integrity_status: 'ready' | 'warning' | 'critical' | 'missing';
  mutation_refs: MemoryArchiveRestoreMutationRef[];
}

export interface MemoryImportResponse {
  imported: Record<string, number>;
  total_imported: number;
}

export type MemoryImportSource =
  | 'auto'
  | 'native_json'
  | 'myrm_archive'
  | 'agentmemory'
  | 'gbrain'
  | 'memweaver'
  | 'claude_code_jsonl'
  | 'hermes'
  | 'openclaw'
  | 'cursor_rules'
  | 'codex'
  | 'claude'
  | 'windsurf'
  | 'trae'
  | 'mem0'
  | 'chatgpt';

export interface MemoryImportMappingItem {
  source_bucket: string;
  target_bucket?: string | null;
  status: 'mapped' | 'partially_mapped' | 'unsupported' | 'dropped';
  item_count: number;
  imported_count: number;
  unmapped_count: number;
  reason: string;
}

export interface MemoryImportDryRunSummary {
  source: Exclude<MemoryImportSource, 'auto'> | 'unknown';
  version: string;
  total_items: number;
  mapped_items: number;
  unmapped_items: number;
  status: 'ready' | 'warning' | 'critical' | 'missing';
}

export interface MemoryImportDryRunResult {
  summary: MemoryImportDryRunSummary;
  mappings: MemoryImportMappingItem[];
  warnings: string[];
  normalized_data: Record<string, Record<string, unknown>[]>;
}

export interface MemoryImportCoverageItem {
  key: string;
  status: 'ready' | 'review' | 'manual' | 'missing';
  label: string;
}

export interface MemoryImportPendingSkill {
  name: string;
  content: string;
  path?: string;
  source?: string;
}

export interface MemoryImportMigrationOptions {
  target_agent_id?: string | null;
  clone_from_agent_id?: string;
  include_episodic?: boolean;
  apply_global_instructions?: boolean;
}

export interface MigrationLanePreviewItem {
  lane: string;
  status: string;
  label: string;
  detail: string;
}

export interface TokenEconomicsComparison {
  skill_count: number;
  source_tokens_per_turn: number;
  myrm_tokens_per_turn: number;
  savings_percent: number;
}

export interface MCPServerPreviewItem {
  name: string;
  type: string;
  command?: string;
  commandPreview?: string;
  url?: string;
  envKeyCount?: number;
  hostSerial?: boolean;
  keepaliveInterval?: number;
  keepaliveIntervalIgnored?: boolean;
}

export interface MemoryImportDryRunResponse {
  dry_run_id: string;
  payload_hash: string;
  expires_at: string;
  result: MemoryImportDryRunResult;
  pending_skills: MemoryImportPendingSkill[];
  coverage_items: MemoryImportCoverageItem[];
  migration_lanes: MigrationLanePreviewItem[];
  token_economics?: TokenEconomicsComparison | null;
  instruction_preview_persona?: string | null;
  instruction_preview_rule_names?: string[];
  instruction_total_chars?: number;
  providers_configured?: boolean;
  mcp_servers_preview?: MCPServerPreviewItem[];
}

export interface MemoryImportConfirmResponse extends MemoryImportResponse {
  import_batch_id: string;
  payload_hash: string;
  source: string;
  transaction_items: number;
  diagnostic_status?: string | null;
  diagnostic_run_id?: string | null;
  target_agent_id?: string | null;
  agent_created?: boolean;
  global_instructions_updated?: boolean;
  workspace_rules_written?: number;
  workspace_rules_skipped?: number;
}

export interface MemoryImportRollbackWarning {
  code: string;
  severity: 'info' | 'warning' | 'error';
  params: Record<string, string | number | boolean>;
}

export interface MemoryImportRollbackPreviewResponse {
  import_batch_id: string;
  source: string;
  total_items: number;
  reversible_items: number;
  items_by_type: Record<string, number>;
  profile_keys: string[];
  warnings: MemoryImportRollbackWarning[];
  skipped_items: number;
  conflict_items: number;
  missing_items: number;
  requires_confirmation: boolean;
}

export interface MemoryImportRollbackRef {
  memory_type: string;
  memory_id: string;
  backend: string;
  reason: string;
}

export interface MemoryImportRollbackResponse {
  import_batch_id: string;
  rolled_back: Record<string, number>;
  total_rolled_back: number;
  source: string;
  conflict_items: number;
  missing_items: number;
  failed_items: number;
  deleted_refs: MemoryImportRollbackRef[];
  missing_refs: MemoryImportRollbackRef[];
  forbidden_refs: MemoryImportRollbackRef[];
  failed_refs: MemoryImportRollbackRef[];
  integrity_status: string;
  instructions_rolled_back?: boolean;
  imported_agent_deleted?: boolean;
}

export const parseMemoryArchiveFile = async (file: File): Promise<MemoryArchivePayload> => {
  if (file.size <= 0) {
    throw new MemoryArchiveFileError('emptyFile', 'Memory archive file is empty.');
  }
  if (file.size > MEMORY_ARCHIVE_FILE_MAX_BYTES) {
    throw new MemoryArchiveFileError('tooLarge', 'Memory archive file is too large.', {
      maxMb: Math.round(MEMORY_ARCHIVE_FILE_MAX_BYTES / 1024 / 1024),
    });
  }

  let raw: unknown;
  try {
    raw = JSON.parse(await file.text()) as unknown;
  } catch {
    throw new MemoryArchiveFileError('invalidJson', 'Memory archive file is not valid JSON.');
  }
  return parseMemoryArchivePayload(raw);
};

export const parseMemoryArchivePayload = (raw: unknown): MemoryArchivePayload => {
  if (!isRecord(raw)) {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive payload must be a JSON object.');
  }

  const manifest = parseMemoryArchiveManifest(raw.manifest);
  if (!isRecord(raw.data)) {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive payload must include a data object.');
  }

  return {
    manifest,
    data: raw.data,
  };
};

export const getDefaultArchiveRestoreSections = (archive: MemoryArchivePayload): MemoryArchiveSectionName[] => {
  const available = archive.manifest.sections.filter((section) => section.status !== 'unsupported');
  const nonEmpty = available.filter((section) => section.item_count > 0);
  const selected = nonEmpty.length > 0 ? nonEmpty : available;
  return MEMORY_ARCHIVE_SECTION_NAMES.filter((name) => selected.some((section) => section.name === name));
};

export const isMemoryArchiveSectionName = (value: unknown): value is MemoryArchiveSectionName =>
  typeof value === 'string' && MEMORY_ARCHIVE_SECTION_NAMES.includes(value as MemoryArchiveSectionName);

const parseMemoryArchiveManifest = (raw: unknown): MemoryArchiveManifest => {
  if (!isRecord(raw)) {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive manifest must be a JSON object.');
  }
  if (raw.format !== 'myrm_memory_archive') {
    throw new MemoryArchiveFileError('unsupportedFormat', 'Only Myrm memory archive files are supported.');
  }
  if (typeof raw.version !== 'number') {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive manifest version must be a number.');
  }
  if (typeof raw.created_at !== 'string' || typeof raw.producer !== 'string') {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive manifest metadata is incomplete.');
  }
  if (!Array.isArray(raw.sections) || raw.sections.length === 0) {
    throw new MemoryArchiveFileError('missingSections', 'Memory archive manifest must include sections.');
  }

  return {
    format: 'myrm_memory_archive',
    version: raw.version,
    created_at: raw.created_at,
    producer: raw.producer,
    sections: raw.sections.map(parseMemoryArchiveSection),
    content_redacted: raw.content_redacted === true,
  };
};

const parseMemoryArchiveSection = (raw: unknown): MemoryArchiveSection => {
  if (!isRecord(raw)) {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive section must be a JSON object.');
  }
  if (!isMemoryArchiveSectionName(raw.name)) {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive section has an unsupported name.');
  }
  if (!isMemoryArchiveSectionStatus(raw.status)) {
    throw new MemoryArchiveFileError('invalidShape', 'Memory archive section has an unsupported status.');
  }
  const itemCount = raw.item_count;
  if (typeof itemCount !== 'number' || !Number.isInteger(itemCount) || itemCount < 0) {
    throw new MemoryArchiveFileError(
      'invalidShape',
      'Memory archive section item_count must be a non-negative integer.',
    );
  }
  const warningCodes = Array.isArray(raw.warning_codes)
    ? raw.warning_codes.filter((warning): warning is string => typeof warning === 'string')
    : [];
  return {
    name: raw.name,
    status: raw.status,
    item_count: itemCount,
    warning_codes: warningCodes,
  };
};

const isMemoryArchiveSectionStatus = (value: unknown): value is MemoryArchiveSectionStatus =>
  typeof value === 'string' && MEMORY_ARCHIVE_SECTION_STATUSES.includes(value as MemoryArchiveSectionStatus);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

export const exportMemoryArchive = async (): Promise<MemoryArchiveExportResponse> => {
  return apiRequest<MemoryArchiveExportResponse>('/memory/archive/export');
};

export const dryRunMemoryArchive = async (archive: MemoryArchivePayload): Promise<MemoryArchiveDryRunResponse> => {
  return apiRequest<MemoryArchiveDryRunResponse>('/memory/archive/dry-run', {
    method: 'POST',
    body: JSON.stringify({ archive }),
  });
};

export const dryRunArchiveRestore = async (
  archive: MemoryArchivePayload,
  sections?: MemoryArchiveSectionName[],
): Promise<{ result: MemoryArchiveRestoreDryRunResult }> => {
  return apiRequest<{ result: MemoryArchiveRestoreDryRunResult }>('/memory/archive/restore/dry-run', {
    method: 'POST',
    body: JSON.stringify({ archive, sections }),
  });
};

export const confirmArchiveRestore = async (
  archive: MemoryArchivePayload,
  payloadHash: string,
  planHash: string,
  sections?: MemoryArchiveSectionName[],
): Promise<{ result: MemoryArchiveRestoreResult }> => {
  return apiRequest<{ result: MemoryArchiveRestoreResult }>('/memory/archive/restore/confirm', {
    method: 'POST',
    body: JSON.stringify({ archive, payload_hash: payloadHash, plan_hash: planHash, sections, skip_duplicates: true }),
  });
};

export const dryRunArchiveRestoreRollback = async (
  restoreBatchId: string,
): Promise<{ result: MemoryArchiveRestoreRollbackPreview }> => {
  return apiRequest<{ result: MemoryArchiveRestoreRollbackPreview }>('/memory/archive/restore/rollback/dry-run', {
    method: 'POST',
    body: JSON.stringify({ restore_batch_id: restoreBatchId }),
  });
};

export const rollbackArchiveRestore = async (
  restoreBatchId: string,
): Promise<{ result: MemoryArchiveRestoreRollbackResult }> => {
  return apiRequest<{ result: MemoryArchiveRestoreRollbackResult }>('/memory/archive/restore/rollback', {
    method: 'POST',
    body: JSON.stringify({ restore_batch_id: restoreBatchId }),
  });
};

export const dryRunImportMemories = async (
  payload: Record<string, unknown>,
  source: MemoryImportSource = 'auto',
  migration?: MemoryImportMigrationOptions,
): Promise<MemoryImportDryRunResponse> => {
  return apiRequest<MemoryImportDryRunResponse>('/memory/import/dry-run', {
    method: 'POST',
    body: JSON.stringify({
      source,
      payload,
      skip_duplicates: true,
      migration: migration ?? {
        clone_from_agent_id: 'builtin-general',
        include_episodic: false,
        apply_global_instructions: true,
      },
    }),
  });
};

export const confirmImportMemories = async (
  dryRunId: string,
  skipDuplicates = true,
): Promise<MemoryImportConfirmResponse> => {
  return apiRequest<MemoryImportConfirmResponse>('/memory/import/confirm', {
    method: 'POST',
    body: JSON.stringify({ dry_run_id: dryRunId, skip_duplicates: skipDuplicates }),
  });
};

export const rollbackMemoryImport = async (
  importBatchId: string,
  options?: { deleteImportedAgent?: boolean },
): Promise<MemoryImportRollbackResponse> => {
  return apiRequest<MemoryImportRollbackResponse>('/memory/import/rollback', {
    method: 'POST',
    body: JSON.stringify({
      import_batch_id: importBatchId,
      delete_imported_agent: options?.deleteImportedAgent ?? false,
    }),
  });
};

export const dryRunRollbackMemoryImport = async (
  importBatchId: string,
): Promise<MemoryImportRollbackPreviewResponse> => {
  return apiRequest<MemoryImportRollbackPreviewResponse>('/memory/import/rollback/dry-run', {
    method: 'POST',
    body: JSON.stringify({ import_batch_id: importBatchId }),
  });
};
