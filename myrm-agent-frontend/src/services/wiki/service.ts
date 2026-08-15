import { getApiUrl, fetchWithTimeout, apiRequest } from '@/lib/api';
import type { WikiClaimStatus } from '@/lib/wiki/claimStatusDisplay';

export function buildWikiApiPath(path: string, agentId?: string | null): string {
  const trimmed = agentId?.trim();
  if (!trimmed) {
    return path;
  }
  const joiner = path.includes('?') ? '&' : '?';
  return `${path}${joiner}agent_id=${encodeURIComponent(trimmed)}`;
}

export function buildWikiAssetUrl(filename: string, agentId?: string | null): string {
  return getApiUrl(buildWikiApiPath(`/wiki/assets/${encodeURIComponent(filename)}`, agentId));
}

export interface WikiEditorSections {
  compiled_truth: string;
  timeline: string;
  tags: string[];
  aliases: string[];
}

export interface Concept {
  name: string;
  content: string;
  content_hash?: string;
  provenance?: string | null;
  source_chat?: string | null;
  source_message?: string | null;
  claims?: WikiClaim[];
  editor_sections?: WikiEditorSections;
}

export type WikiSourceLevel = 'L0' | 'L1' | 'L2';

export interface WikiSourceSnippet {
  path: string;
  name: string;
  snippet: string;
  section: string;
  level: WikiSourceLevel;
  claim_id?: string;
  claim_text?: string;
  evidence_path?: string;
  line_range?: string;
  claim_status?: WikiClaimStatus;
  claim_confidence?: number;
  snapshot_status?: 'verified' | 'stale' | 'missing';
  resource_uri?: string;
  superseded_from_uri?: string;
  hit_kind?: 'concept' | 'asset';
  asset_filename?: string;
}

export interface WikiClaimEvidence {
  kind: string;
  source_id: string;
  path: string;
  lines: string;
  weight: number;
  confidence: number;
  note: string;
  content_sha256?: string;
  updated_at?: string;
  snapshot_status?: 'verified' | 'stale' | 'missing';
  resource_uri?: string;
  superseded_from_uri?: string;
}

export interface WikiClaim {
  id: string;
  text: string;
  status: string;
  confidence: number;
  updated_at?: string;
  evidence: WikiClaimEvidence[];
}

export type WikiHealthIssueActionKind = 'repair' | 'recompile' | 'navigate' | 'info';

export interface WikiHealthIssue {
  issue_type: string;
  severity: string;
  location: string;
  description: string;
  action_kind: WikiHealthIssueActionKind;
  suggested_fix?: string | null;
}

export interface WikiHealthReport {
  mode: 'structural' | 'full';
  generated_at: string;
  open_actions_count: number;
  issues_found: number;
  issues: WikiHealthIssue[];
  drift_sampled: boolean;
  drift_checked_at?: string | null;
  duplicate_groups_pending: number;
  synthesis_pending: number;
}

export interface WikiGraphInsightRecord {
  [key: string]: string | number | boolean | null | undefined;
}

export interface WikiGraphInsights {
  unexpected_connections: WikiGraphInsightRecord[];
  knowledge_gaps: WikiGraphInsightRecord[];
  communities: WikiGraphInsightRecord[];
}

export interface WikiMaintainResponse {
  issues_found: number;
  issues_fixed: number;
  connections_discovered: number;
  duration_ms: number;
  open_actions_count: number;
  raw_security_removed: number;
  raw_security_removed_paths: string[];
  issues: WikiHealthIssue[];
}

export type WikiQueryMode = 'auto' | 'raw_claim';

export interface WikiQueryRequestBody {
  question: string;
  mode: WikiQueryMode;
}

export function buildWikiQueryRequestBody(
  question: string,
  mode: WikiQueryMode = 'auto',
): WikiQueryRequestBody {
  return { question, mode };
}

export interface WikiRetrievalTraceIndexHit {
  link_name: string;
  summary: string;
  score: number;
  page_type?: string;
}

export interface WikiRetrievalSeedTraceItem {
  concept_name: string;
  score: number;
  source: string;
}

export interface WikiRetrievalTrace {
  index_hits: WikiRetrievalTraceIndexHit[];
  seeds: WikiRetrievalSeedTraceItem[];
  sidecar_directories: string[];
  selected_concepts: string[];
}

export interface WikiQueryResponse {
  answer: string;
  related_articles: string[];
  source_snippets: WikiSourceSnippet[];
  confidence_score?: number;
  retrieval_trace?: WikiRetrievalTrace | null;
}

export interface CompileRunStatus {
  state: 'running' | 'paused';
  pause_reason: string;
  primary_error_kind: string;
  phase?: 'idle' | 'structure_survey' | 'semantic_compile' | 'postprocess';
  facet_count?: number;
  warning_count?: number;
  survey_skipped?: boolean;
}

export interface WikiQueueStats {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  [key: string]: number;
}

export interface QueueStatus {
  stats: WikiQueueStats;
  pending_items: Array<{
    id: number;
    file_path: string;
    file_type?: string;
    status: string;
    retry_count?: number;
    error_kind?: string;
    error_message?: string;
    created_at: string;
    updated_at?: string;
  }>;
  failed_items: Array<{
    id: number;
    file_path: string;
    status: string;
    retry_count?: number;
    error_kind?: string;
    error_message?: string;
    created_at: string;
    updated_at?: string;
  }>;
  compile_run?: CompileRunStatus | null;
}

export interface PendingEdit {
  id: number;
  concept_name: string;
  proposed_content: string;
  provenance?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PendingEditsResponse {
  stats: Record<string, number>;
  pending_edits: PendingEdit[];
}

export interface WikiCompoundRequestBody {
  concept_name: string;
  source_chat: string;
  source_message: string;
}

export interface WikiCompoundResponse {
  success: boolean;
  pending_edit_id: number;
  concept_name: string;
  message: string;
}

export type WikiApplyCaller = 'agent' | 'settings' | 'chat';

export type WikiApplyOp =
  | 'update_metadata'
  | 'patch_compiled_truth'
  | 'append_timeline'
  | 'create_note'
  | 'replace_full_document';

export interface WikiApplyRequestBody {
  op: WikiApplyOp;
  concept_name: string;
  compiled_truth?: string;
  timeline_entry?: string;
  content?: string;
  body?: string;
  tags?: string[];
  aliases?: string[];
  sources?: string[];
  clear_confidence?: boolean;
  page_type?: string;
  provenance?: string;
  metadata?: Record<string, string>;
  canonical_id?: string;
  if_match?: string;
}

export type WikiDedupTier = 'exact' | 'normalized' | 'near';
export type WikiDedupDispositionAction = 'trash' | 'exclude' | 'dismiss' | 'defer';

export interface WikiDedupMember {
  relative_path: string;
  size_bytes: number;
  mtime_ns: number;
}

export interface WikiDedupGroup {
  group_id: number;
  tier: WikiDedupTier;
  fingerprint: string;
  recommended_keep_path: string;
  status: 'open' | 'deferred' | 'resolved';
  members: WikiDedupMember[];
}

export interface WikiDedupMemberSnippet {
  relative_path: string;
  snippet: string;
}

export interface WikiDedupScanResponse {
  accepted: boolean;
  skipped: boolean;
  skipped_reason?: string | null;
  files_scanned?: number;
  groups_found?: number;
  open_groups?: number;
  exact_groups?: number;
  normalized_groups?: number;
  near_groups?: number;
  duration_ms?: number;
}

export interface WikiDedupDispositionResponse {
  group_id: number;
  action: WikiDedupDispositionAction;
  affected_paths: string[];
  compile_jobs_prevented?: number;
}

export interface WikiDedupProgress {
  phase: 'idle' | 'scanning' | 'grouping' | 'done' | 'failed';
  files_scanned: number;
  files_total: number;
  groups_found: number;
  message?: string;
}

export interface WikiDedupTrashedEntry {
  relative_path: string;
  trash_relpath: string;
  content_hash: string;
  created_at: string;
}

export interface WikiDedupExcludedEntry {
  relative_path: string;
  reason: string;
  created_at: string;
}

export interface WikiDedupVaultHygiene {
  trashed: WikiDedupTrashedEntry[];
  excluded: WikiDedupExcludedEntry[];
}

export interface WikiApplyResponse {
  success: boolean;
  op: WikiApplyOp;
  concept_name: string;
  message: string;
  created?: boolean;
  appended?: boolean;
  content_hash?: string;
}

export interface OperationResult {
  success: boolean;
  message: string;
}

export interface RepairTypesResponse {
  success: boolean;
  files_scanned: number;
  files_repaired: number;
  files_skipped: number;
  message: string;
}

export interface WikiCompileResponse {
  concepts_count: number;
  articles_generated: number;
  backlinks_created: number;
  duration_ms: number;
  articles_pending: number;
  articles_published: number;
  articles_blocked: number;
  synthesis_pending: number;
  compile_run?: CompileRunStatus | null;
}

export interface RepairPublicationResponse {
  success: boolean;
  files_scanned: number;
  files_repaired: number;
  files_skipped: number;
  files_skipped_intentional_drafts?: number;
  reindexed: number;
  message: string;
}

export interface ReindexVectorsResponse {
  success: boolean;
  scanned: number;
  reindexed: number;
  concepts_reindexed: number;
  sidecars_reindexed: number;
  assets_indexed: number;
  skipped_drafts: number;
  failed: number;
  errors: string[];
  message: string;
}

export interface ConceptListResponse {
  concepts: string[];
  total: number;
  has_more: boolean;
}

export interface TreeNode {
  id: string;
  name: string;
  is_dir: boolean;
  ingest_status?: 'tracked-clean' | 'tracked-modified' | null;
  children?: TreeNode[];
}

export interface ImportResultResponse {
  success: boolean;
  files_scanned: number;
  files_enqueued: number;
  files_skipped_conflict?: number;
  files_superseded?: number;
  files_security_blocked?: number;
  files_security_redacted?: number;
  conflict_paths?: string[];
  security_blocked_paths?: string[];
  security_redacted_paths?: string[];
  message: string;
}

export interface ObsidianImportResultResponse {
  success: boolean;
  files_scanned: number;
  files_processed: number;
  files_skipped: number;
  files_skipped_conflict?: number;
  files_superseded?: number;
  files_security_blocked?: number;
  files_security_redacted?: number;
  conflict_paths?: string[];
  security_blocked_paths?: string[];
  security_redacted_paths?: string[];
  tags_extracted: number;
  images_copied: number;
  message: string;
}

export type WikiImportConflictPolicy = 'skip' | 'supersede';

export interface WikiImportConflictOptions {
  onConflict?: WikiImportConflictPolicy;
  supersedeReason?: string;
}

async function downloadWikiExportBlob(path: string): Promise<void> {
  const response = await fetchWithTimeout(path, {}, 120000);
  if (!response.ok) {
    throw new Error('Wiki export failed');
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  const disposition = response.headers.get('Content-Disposition');
  anchor.download = disposition?.match(/filename="(.+)"/)?.[1] ?? 'myrm_wiki_export.zip';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export const wikiService = {
  getTree: async (agentId?: string | null): Promise<TreeNode[]> => {
    return apiRequest<TreeNode[]>(buildWikiApiPath('/wiki/tree', agentId));
  },

  getRawTree: async (agentId?: string | null): Promise<TreeNode[]> => {
    return apiRequest<TreeNode[]>(buildWikiApiPath('/wiki/raw/tree', agentId));
  },

  createFolder: async (path: string, agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/tree/folder', agentId), {
      method: 'POST',
      body: JSON.stringify({ path }),
    });
  },

  moveNode: async (sourcePath: string, targetPath: string, agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/tree/move', agentId), {
      method: 'PUT',
      body: JSON.stringify({ source_path: sourcePath, target_path: targetPath }),
    });
  },

  deleteFolder: async (path: string, agentId?: string | null): Promise<OperationResult> => {
    const params = new URLSearchParams();
    params.append('path', path);
    return apiRequest<OperationResult>(buildWikiApiPath(`/wiki/tree/folder?${params.toString()}`, agentId), {
      method: 'DELETE',
    });
  },

  listConcepts: async (
    query?: string,
    limit: number = 100,
    offset: number = 0,
    agentId?: string | null,
  ): Promise<ConceptListResponse> => {
    const params = new URLSearchParams();
    if (query) {params.append('query', query);}
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());
    return apiRequest<ConceptListResponse>(buildWikiApiPath(`/wiki/concepts?${params.toString()}`, agentId));
  },

  queryWiki: async (
    question: string,
    mode: WikiQueryMode = 'auto',
    agentId?: string | null,
  ): Promise<WikiQueryResponse> => {
    return apiRequest<WikiQueryResponse>(buildWikiApiPath('/wiki/query', agentId), {
      method: 'POST',
      body: JSON.stringify(buildWikiQueryRequestBody(question, mode)),
    });
  },

  getConcept: async (name: string, agentId?: string | null): Promise<Concept> => {
    return apiRequest<Concept>(buildWikiApiPath(`/wiki/concepts/${encodeURIComponent(name)}`, agentId));
  },

  applyWiki: async (
    body: WikiApplyRequestBody,
    agentId?: string | null,
    caller: WikiApplyCaller = 'settings',
  ): Promise<WikiApplyResponse> => {
    const path = buildWikiApiPath(`/wiki/apply?caller=${encodeURIComponent(caller)}`, agentId);
    return apiRequest<WikiApplyResponse>(path, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  compoundWiki: async (
    body: WikiCompoundRequestBody,
    agentId?: string | null,
  ): Promise<WikiCompoundResponse> => {
    return apiRequest<WikiCompoundResponse>(buildWikiApiPath('/wiki/compound', agentId), {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  deleteConcept: async (name: string, agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath(`/wiki/concepts/${encodeURIComponent(name)}`, agentId), {
      method: 'DELETE',
    });
  },

  deleteRawSource: async (
    path: string,
    forgetReason: string,
    agentId?: string | null,
  ): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath(`/wiki/raw/${encodeURIComponent(path)}`, agentId), {
      method: 'DELETE',
      body: JSON.stringify({ forget_reason: forgetReason }),
    });
  },

  getQueueStatus: async (agentId?: string | null): Promise<QueueStatus> => {
    return apiRequest<QueueStatus>(buildWikiApiPath('/wiki/queue', agentId));
  },

  cancelQueue: async (agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/queue/cancel', agentId), {
      method: 'POST',
    });
  },

  retryFailedQueue: async (agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/queue/retry', agentId), {
      method: 'POST',
    });
  },

  retryAllFailedQueue: async (agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/queue/retry-all', agentId), {
      method: 'POST',
    });
  },

  resumeCompileCircuit: async (agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/queue/resume-circuit', agentId), {
      method: 'POST',
    });
  },

  getPendingEdits: async (agentId?: string | null): Promise<PendingEditsResponse> => {
    return apiRequest<PendingEditsResponse>(buildWikiApiPath('/wiki/pending', agentId));
  },

  approveEdit: async (id: number, modifiedContent?: string, agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath(`/wiki/pending/${id}/approve`, agentId), {
      method: 'POST',
      body: modifiedContent !== undefined ? JSON.stringify({ modified_content: modifiedContent }) : undefined,
    });
  },

  rejectEdit: async (id: number, agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath(`/wiki/pending/${id}/reject`, agentId), {
      method: 'POST',
    });
  },

  ingestArtifact: async (artifactId: string, agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/ingest', agentId), {
      method: 'POST',
      body: JSON.stringify({ artifact_id: artifactId }),
    });
  },

  importFolder: async (
    folderPath: string,
    extensions: string[] = ['.md', '.txt', '.org'],
    autoCompile: boolean = true,
    agentId?: string | null,
    conflictOptions?: WikiImportConflictOptions,
  ): Promise<ImportResultResponse> => {
    return apiRequest<ImportResultResponse>(buildWikiApiPath('/wiki/import/folder', agentId), {
      method: 'POST',
      body: JSON.stringify({
        folder_path: folderPath,
        extensions,
        auto_compile: autoCompile,
        on_conflict: conflictOptions?.onConflict ?? 'skip',
        supersede_reason: conflictOptions?.supersedeReason ?? '',
      }),
    });
  },

  importZip: async (
    file: File,
    extensions: string = '.md,.txt,.org',
    autoCompile: boolean = true,
    agentId?: string | null,
    conflictOptions?: WikiImportConflictOptions,
  ): Promise<ImportResultResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    params.append('extensions', extensions);
    params.append('auto_compile', autoCompile.toString());
    params.append('on_conflict', conflictOptions?.onConflict ?? 'skip');
    if (conflictOptions?.supersedeReason) {
      params.append('supersede_reason', conflictOptions.supersedeReason);
    }
    return apiRequest<ImportResultResponse>(buildWikiApiPath(`/wiki/import/zip?${params.toString()}`, agentId), {
      method: 'POST',
      body: formData,
    });
  },

  importObsidianFolder: async (
    vaultPath: string,
    autoCompile: boolean = true,
    agentId?: string | null,
    conflictOptions?: WikiImportConflictOptions,
  ): Promise<ObsidianImportResultResponse> => {
    return apiRequest<ObsidianImportResultResponse>(buildWikiApiPath('/wiki/import/obsidian', agentId), {
      method: 'POST',
      body: JSON.stringify({
        vault_path: vaultPath,
        auto_compile: autoCompile,
        on_conflict: conflictOptions?.onConflict ?? 'skip',
        supersede_reason: conflictOptions?.supersedeReason ?? '',
      }),
    });
  },

  importObsidianZip: async (
    file: File,
    autoCompile: boolean = true,
    agentId?: string | null,
    conflictOptions?: WikiImportConflictOptions,
  ): Promise<ObsidianImportResultResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    params.append('auto_compile', autoCompile.toString());
    params.append('on_conflict', conflictOptions?.onConflict ?? 'skip');
    if (conflictOptions?.supersedeReason) {
      params.append('supersede_reason', conflictOptions.supersedeReason);
    }
    return apiRequest<ObsidianImportResultResponse>(
      buildWikiApiPath(`/wiki/import/obsidian-zip?${params.toString()}`, agentId),
      {
        method: 'POST',
        body: formData,
      },
    );
  },

  repairPageTypes: async (agentId?: string | null): Promise<RepairTypesResponse> => {
    return apiRequest<RepairTypesResponse>(buildWikiApiPath('/wiki/repair-types', agentId), {
      method: 'POST',
    });
  },

  compileWiki: async (agentId?: string | null): Promise<WikiCompileResponse> => {
    return apiRequest<WikiCompileResponse>(buildWikiApiPath('/wiki/compile', agentId), {
      method: 'POST',
    });
  },

  repairPublication: async (agentId?: string | null): Promise<RepairPublicationResponse> => {
    return apiRequest<RepairPublicationResponse>(buildWikiApiPath('/wiki/repair-publication', agentId), {
      method: 'POST',
    });
  },

  reindexVectors: async (agentId?: string | null): Promise<ReindexVectorsResponse> => {
    return apiRequest<ReindexVectorsResponse>(buildWikiApiPath('/wiki/reindex-vectors', agentId), {
      method: 'POST',
    });
  },

  getHealthReport: async (agentId?: string | null): Promise<WikiHealthReport> => {
    return apiRequest<WikiHealthReport>(buildWikiApiPath('/wiki/health-report', agentId));
  },

  getGraphInsights: async (agentId?: string | null): Promise<WikiGraphInsights> => {
    return apiRequest<WikiGraphInsights>(buildWikiApiPath('/wiki/graph/insights', agentId));
  },

  maintainWiki: async (
    mode: 'structural' | 'full',
    agentId?: string | null,
  ): Promise<WikiMaintainResponse> => {
    const params = new URLSearchParams({ mode });
    return apiRequest<WikiMaintainResponse>(
      buildWikiApiPath(`/wiki/maintain?${params.toString()}`, agentId),
      { method: 'POST' },
    );
  },

  exportVault: async (agentId?: string | null): Promise<void> => {
    await downloadWikiExportBlob(buildWikiApiPath('/wiki/portability/export', agentId));
  },

  revealWikiVault: async (agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/vault/reveal', agentId), {
      method: 'POST',
    });
  },

  openWikiVaultInObsidian: async (agentId?: string | null): Promise<OperationResult> => {
    return apiRequest<OperationResult>(buildWikiApiPath('/wiki/vault/open-obsidian', agentId), {
      method: 'POST',
    });
  },

  getWikiIgnore: async (agentId?: string | null): Promise<{ content: string }> => {
    return apiRequest<{ content: string }>(buildWikiApiPath('/wiki/wikiignore', agentId));
  },

  putWikiIgnore: async (content: string, agentId?: string | null): Promise<{ content: string }> => {
    return apiRequest<{ content: string }>(buildWikiApiPath('/wiki/wikiignore', agentId), {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  },

  getWikiDedupVaultHygiene: async (agentId?: string | null): Promise<WikiDedupVaultHygiene> => {
    return apiRequest<WikiDedupVaultHygiene>(buildWikiApiPath('/wiki/dedup/vault-hygiene', agentId));
  },

  getWikiDuplicateGroups: async (agentId?: string | null): Promise<WikiDedupGroup[]> => {
    return apiRequest<WikiDedupGroup[]>(buildWikiApiPath('/wiki/dedup/groups', agentId));
  },

  getWikiDedupGroupSnippets: async (
    groupId: number,
    agentId?: string | null,
  ): Promise<WikiDedupMemberSnippet[]> => {
    return apiRequest<WikiDedupMemberSnippet[]>(
      buildWikiApiPath(`/wiki/dedup/groups/${groupId}/snippets`, agentId),
    );
  },

  getWikiDedupProgress: async (agentId?: string | null): Promise<WikiDedupProgress> => {
    return apiRequest<WikiDedupProgress>(buildWikiApiPath('/wiki/dedup/progress', agentId));
  },

  scanWikiDuplicates: async (
    agentId?: string | null,
    incremental?: boolean,
  ): Promise<WikiDedupScanResponse> => {
    const basePath = buildWikiApiPath('/wiki/dedup/scan', agentId);
    const joiner = basePath.includes('?') ? '&' : '?';
    const path = incremental === false ? `${basePath}${joiner}incremental=false` : basePath;
    return apiRequest<WikiDedupScanResponse>(path, { method: 'POST' });
  },

  applyWikiDuplicateDisposition: async (
    groupId: number,
    action: WikiDedupDispositionAction,
    reason: string,
    agentId?: string | null,
  ): Promise<WikiDedupDispositionResponse> => {
    return apiRequest<WikiDedupDispositionResponse>(
      buildWikiApiPath(`/wiki/dedup/groups/${groupId}/disposition`, agentId),
      {
        method: 'POST',
        body: JSON.stringify({ action, reason }),
      },
    );
  },

  restoreWikiDedupTrashedRaw: async (
    relativePath: string,
    agentId?: string | null,
  ): Promise<WikiDedupTrashedEntry> => {
    return apiRequest<WikiDedupTrashedEntry>(buildWikiApiPath('/wiki/dedup/trash/restore', agentId), {
      method: 'POST',
      body: JSON.stringify({ relative_path: relativePath }),
    });
  },

  undoWikiDedupExcludedRaw: async (
    relativePath: string,
    agentId?: string | null,
  ): Promise<WikiDedupExcludedEntry> => {
    return apiRequest<WikiDedupExcludedEntry>(buildWikiApiPath('/wiki/dedup/excluded/undo', agentId), {
      method: 'POST',
      body: JSON.stringify({ relative_path: relativePath }),
    });
  },
};
