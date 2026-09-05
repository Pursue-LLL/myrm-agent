/**
 * 技能 API 服务
 *
 * [INPUT]
 * @/lib/api::apiRequest,fetchWithTimeout (POS: frontend API request helper)
 * @/store/skill/types::Skill 等 DTO (POS: 技能 store 类型)
 *
 * [OUTPUT]
 * 技能 CRUD、生命周期、用户配置、扫描、本机路径、审批 API 函数与 DTO。
 *
 * [POS]
 * Frontend 技能 API client。`/skills/*` REST 契约。
 */

/**
 * 技能 API 服务
 */

import { apiRequest, fetchWithTimeout } from '@/lib/api';
import type {
  Skill,
  SkillListResponse,
  SkillLifecycleAction,
  SkillLifecycleStatus,
  UserSkillConfig,
  UpdateUserSkillConfigRequest,
  SkillSortBy,
  SkillSortOrder,
  LocalSkillPathsResponse,
} from '@/store/skill/types';

const SKILLS_API_PREFIX = '/skills';

/** Remote skill operations (preview/analyze/install) download from GitHub or
 * archives; the default 30s request timeout would abort mid-operation on slow
 * networks even though the server eventually succeeds. Keep the client request
 * open well beyond the server-side zip download cap (30s) and git clone cap (60s). */
const SKILL_REMOTE_OP_TIMEOUT_MS = 120_000;

export interface ScanFinding {
  threat_type: string;
  severity: number;
  description: string;
  line_number: number | null;
}

export interface ListSkillsParams {
  type?: 'prebuilt' | 'local';
  sortBy?: SkillSortBy;
  order?: SkillSortOrder;
}

/**
 * 获取技能列表
 * @param params 查询参数
 */
export async function listSkills(params: ListSkillsParams = {}): Promise<SkillListResponse> {
  const { type, sortBy = 'name', order = 'asc' } = params;

  const queryParams = new URLSearchParams();
  if (type) {
    queryParams.append('type', type);
  }
  queryParams.append('sort_by', sortBy);
  queryParams.append('order', order);

  const endpoint = `${SKILLS_API_PREFIX}?${queryParams.toString()}`;

  return apiRequest<SkillListResponse>(endpoint);
}

/**
 * 获取技能详情
 * @param skillId 技能 ID
 */
export async function getSkill(skillId: string): Promise<Skill> {
  return apiRequest<Skill>(`${SKILLS_API_PREFIX}/${skillId}`);
}

/**
 * 在系统文件管理器中打开本地技能目录
 * @param skillId 技能 ID
 */
export async function revealSkill(skillId: string): Promise<{ status: string; path: string }> {
  return apiRequest<{ status: string; path: string }>(`${SKILLS_API_PREFIX}/${skillId}/reveal`, {
    method: 'POST',
  });
}

/**
 * 获取技能文件内容（如 SKILL.md）
 * @param skillId 技能 ID
 * @param filename 文件名
 */
export async function getSkillFile(skillId: string, filename: string): Promise<string> {
  const response = await fetchWithTimeout(`${SKILLS_API_PREFIX}/${skillId}/files/${filename}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch skill file: ${response.statusText}`);
  }

  return response.text();
}

export interface UpdateSkillFileResponse {
  status: string;
  skill_id: string;
  filename: string;
  is_clean: boolean;
  trust_recommendation: string;
  findings_count: number;
}

/**
 * 保存技能文件内容并自动触发安全审计
 * @param skillId 技能 ID
 * @param filename 文件名
 * @param content 文件正文
 */
export async function saveSkillFile(
  skillId: string,
  filename: string,
  content: string,
): Promise<UpdateSkillFileResponse> {
  return apiRequest<UpdateSkillFileResponse>(`${SKILLS_API_PREFIX}/${skillId}/files/${filename}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  });
}

/**
 * 获取用户技能配置
 */
export async function getUserSkillConfig(): Promise<UserSkillConfig> {
  return apiRequest<UserSkillConfig>(`${SKILLS_API_PREFIX}/config`);
}

/**
 * 更新用户技能配置
 * @param request 更新请求
 */
export async function updateUserSkillConfig(request: UpdateUserSkillConfigRequest): Promise<UserSkillConfig> {
  return apiRequest<UserSkillConfig>(`${SKILLS_API_PREFIX}/config`, {
    method: 'PUT',
    body: JSON.stringify(request),
  });
}

/**
 * 获取用户可用的技能列表
 */
export async function getUserAvailableSkills(): Promise<SkillListResponse> {
  return apiRequest<SkillListResponse>(`${SKILLS_API_PREFIX}/available`);
}

// ========== Enable/Disable with security scan ==========

export interface EnableSkillResponse {
  skill_id: string;
  enabled: boolean;
  blocked: boolean;
  scan_findings: ScanFinding[];
  pending_approval?: boolean;
  required_permissions?: string[];
}

export async function enableSkill(skillId: string, force: boolean = false): Promise<EnableSkillResponse> {
  const params = force ? '?force=true' : '';
  return apiRequest<EnableSkillResponse>(`${SKILLS_API_PREFIX}/${skillId}/enable${params}`, { method: 'POST' });
}

export async function disableSkill(skillId: string): Promise<EnableSkillResponse> {
  return apiRequest<EnableSkillResponse>(`${SKILLS_API_PREFIX}/${skillId}/disable`, { method: 'POST' });
}

// ========== Skill env var management ==========

export interface SkillEnvVarsResponse {
  skill_id: string;
  env_vars: Record<string, string>;
  required_env: string[];
  primary_env: string | null;
}

export async function getSkillEnvVars(skillId: string): Promise<SkillEnvVarsResponse> {
  return apiRequest<SkillEnvVarsResponse>(`${SKILLS_API_PREFIX}/${skillId}/env`);
}

export async function updateSkillEnvVars(
  skillId: string,
  envVars: Record<string, string>,
): Promise<SkillEnvVarsResponse> {
  return apiRequest<SkillEnvVarsResponse>(`${SKILLS_API_PREFIX}/${skillId}/env`, {
    method: 'PUT',
    body: JSON.stringify({ env_vars: envVars }),
  });
}

// ========== 本地技能管理 API ==========

/**
 * 获取用户配置的本地技能路径
 */
export async function getLocalSkillPaths(): Promise<LocalSkillPathsResponse> {
  return apiRequest<LocalSkillPathsResponse>(`${SKILLS_API_PREFIX}/local/paths`);
}

/**
 * 更新用户的本地技能路径配置
 * @param paths 路径列表
 */
export async function updateLocalSkillPaths(paths: string[]): Promise<LocalSkillPathsResponse> {
  return apiRequest<LocalSkillPathsResponse>(`${SKILLS_API_PREFIX}/local/paths`, {
    method: 'PUT',
    body: JSON.stringify({ paths }),
  });
}

/**
 * 扫描本地技能
 */
export async function scanLocalSkills(): Promise<SkillListResponse> {
  return apiRequest<SkillListResponse>(`${SKILLS_API_PREFIX}/local/scan`, {
    method: 'POST',
  });
}

/** 切换本地技能响应 */
export interface ToggleLocalSkillResponse {
  skill_id: string;
  enabled: boolean;
}

/**
 * 切换本地技能的启用状态
 * @param skillId 本地技能 ID
 */
export async function toggleLocalSkill(skillId: string): Promise<ToggleLocalSkillResponse> {
  return apiRequest<ToggleLocalSkillResponse>(`${SKILLS_API_PREFIX}/local/toggle`, {
    method: 'POST',
    body: JSON.stringify({ skill_id: skillId }),
  });
}

// ========== 技能打包下载/上传 API ==========

/** 技能包信息 */
export interface SkillPackageInfo {
  name: string;
  description: string;
  version: string;
  author: string | null;
  files: string[];
  is_valid: boolean;
  validation_errors: string[];
}

/** 上传技能响应 */
export interface UploadSkillResponse {
  success: boolean;
  skill_id: string | null;
  skill_name: string | null;
  error: string | null;
  restored_eval_cases: number;
}

export interface RedactionResponse {
  line_number: number;
  original: string;
  redacted: string;
  reason: string;
}

export interface PackagePreviewResponse {
  success: boolean;
  is_safe: boolean;
  error: string | null;
  redactions: Record<string, RedactionResponse[]> | null;
  eval_cases_count: number;
}

/**
 * 预览技能打包结果，检查是否有敏感信息
 * @param skillId 技能 ID
 */
export async function previewSkillPackage(skillId: string): Promise<PackagePreviewResponse> {
  return apiRequest<PackagePreviewResponse>(`${SKILLS_API_PREFIX}/${skillId}/preview`);
}

/**
 * 下载技能为 ZIP 包
 * @param skillId 技能 ID
 * @param applyRedactions 是否应用脱敏
 * @param ignoredRedactions 忽略脱敏的索引字典 (filename -> indices)
 * @returns blob 与后端 Content-Disposition 提供的文件名
 */
export async function downloadSkill(
  skillId: string,
  applyRedactions: boolean = false,
  ignoredRedactions: Record<string, number[]> = {},
  exportFormat: 'agent_plugin' | 'raw_skill' = 'agent_plugin',
): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetchWithTimeout(`${SKILLS_API_PREFIX}/${skillId}/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
    },
    body: JSON.stringify({
      apply_redactions: applyRedactions,
      ignored_redactions: ignoredRedactions,
      export_format: exportFormat,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`下载失败: ${error}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const filenameMatch = disposition.match(/filename="?([^";]+)"?/);
  return { blob, filename: filenameMatch ? filenameMatch[1] : null };
}

/**
 * 上传技能 ZIP 包并注册
 * @param file ZIP 文件
 * @param force 是否强制覆盖同名技能
 */
export async function uploadSkill(file: File, force: boolean = false): Promise<UploadSkillResponse> {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<UploadSkillResponse>(`${SKILLS_API_PREFIX}/upload?force=${force}`, {
    method: 'POST',
    body: formData,
  });
}

/**
 * 验证技能 ZIP 包（不注册）
 * @param file ZIP 文件
 */
export async function validateSkillZip(file: File): Promise<SkillPackageInfo> {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest<SkillPackageInfo>(`${SKILLS_API_PREFIX}/validate`, {
    method: 'POST',
    body: formData,
  });
}

/**
 * 打包工作空间目录为 ZIP
 * @param chatId 会话 ID
 * @param directory 要打包的目录路径
 * @param containerId 容器 ID（Docker 模式）
 */
export async function packageWorkspaceDirectory(
  chatId: string,
  directory: string = '',
  containerId?: string,
): Promise<Blob> {
  const formData = new FormData();
  formData.append('chat_id', chatId);
  formData.append('directory', directory);
  if (containerId) {
    formData.append('container_id', containerId);
  }

  const response = await fetchWithTimeout('/storage/workspace/package', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`打包失败: ${error}`);
  }

  return response.blob();
}

// ========== Skill Discovery API ==========

export interface DiscoverySearchResult {
  id: string;
  name: string;
  description: string;
  source: string;
  author: string;
  install_url: string;
  install_method: string;
  version: string;
  stars: number;
  downloads: number;
  tags: string[];
  readme_url: string | null;
  subdirectory: string | null;
  installed_version: string;
  upgrade_available: boolean;
  installed_skill_id?: string;
  package_type?: 'skill' | 'agent_plugin' | string;
  keywords?: string[];
  declared_mcp_servers?: string[];
}

export interface DiscoverySearchResponse {
  results: DiscoverySearchResult[];
  total: number;
  query: string;
}

export interface DiscoveryInstallResponse {
  success: boolean;
  skill_name: string;
  skill_id: string;
  installed_path: string;
  version?: string;
  error: string;
  /** Machine-readable error code (archive_security.* etc.) aligned with server
   * SkillInstallResponse; empty when the failure is not security-classified. */
  error_code?: string;
  mounted?: boolean;
  mount_agent_id?: string;
  mount_skill_id?: string;
  mount_already_present?: boolean;
  mount_error?: string;
  allowlist_appended?: boolean;
  allowlist_append_error?: string;
  installed_skills?: string[];
  declared_mcp_servers?: string[];
}

export interface DiscoveryInstallOptions {
  agentId?: string;
  mountToAgent?: boolean;
}

export interface DiscoveryPreviewResponse {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  files: string[];
  scan_findings: ScanFinding[];
  is_clean: boolean;
  package_type?: 'skill' | 'agent_plugin' | string;
  installed_skills?: string[];
  declared_mcp_servers?: string[];
}

export async function searchDiscoverySkills(
  query: string,
  limit: number = 30,
  userId?: string,
  packageType: 'all' | 'skill' | 'agent_plugin' = 'all',
): Promise<DiscoverySearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (userId) {
    params.set('user_id', userId);
  }
  if (packageType && packageType !== 'all') {
    params.set('package_type', packageType);
  }
  return apiRequest<DiscoverySearchResponse>(`${SKILLS_API_PREFIX}/discovery/search?${params}`);
}

export async function previewDiscoverySkill(skillId: string, source: string): Promise<DiscoveryPreviewResponse> {
  return apiRequest<DiscoveryPreviewResponse>(`${SKILLS_API_PREFIX}/discovery/preview`, {
    method: 'POST',
    timeout: SKILL_REMOTE_OP_TIMEOUT_MS,
    body: JSON.stringify({ skill_id: skillId, source }),
  });
}

export async function installDiscoverySkill(
  skillId: string,
  source: string,
  options?: DiscoveryInstallOptions,
): Promise<DiscoveryInstallResponse> {
  return apiRequest<DiscoveryInstallResponse>(`${SKILLS_API_PREFIX}/discovery/install`, {
    method: 'POST',
    timeout: SKILL_REMOTE_OP_TIMEOUT_MS,
    body: JSON.stringify({
      skill_id: skillId,
      source,
      agent_id: options?.agentId,
      mount_to_agent: options?.mountToAgent ?? true,
    }),
  });
}

export async function uninstallDiscoverySkill(
  skillId: string,
  force: boolean = false,
): Promise<DiscoveryInstallResponse> {
  return apiRequest<DiscoveryInstallResponse>(`${SKILLS_API_PREFIX}/discovery/uninstall`, {
    method: 'POST',
    body: JSON.stringify({ skill_id: skillId, force }),
  });
}

export interface SkillUrlInfo {
  url: string;
  name: string;
  description: string;
  is_installed: boolean;
}

export interface DiscoveryAnalyzeUrlResponse {
  urls: SkillUrlInfo[];
}

export async function analyzeDiscoveryUrl(url: string): Promise<DiscoveryAnalyzeUrlResponse> {
  return apiRequest<DiscoveryAnalyzeUrlResponse>(`${SKILLS_API_PREFIX}/discovery/analyze-url`, {
    method: 'POST',
    timeout: SKILL_REMOTE_OP_TIMEOUT_MS,
    body: JSON.stringify({ url }),
  });
}

export async function installDiscoverySkillFromUrl(
  url: string,
  options?: DiscoveryInstallOptions,
): Promise<DiscoveryInstallResponse> {
  return apiRequest<DiscoveryInstallResponse>(`${SKILLS_API_PREFIX}/discovery/install-from-url`, {
    method: 'POST',
    timeout: SKILL_REMOTE_OP_TIMEOUT_MS,
    body: JSON.stringify({
      url,
      agent_id: options?.agentId,
      mount_to_agent: options?.mountToAgent ?? true,
    }),
  });
}

export async function trustSkill(skillId: string): Promise<{ skill_id: string; trust: string }> {
  return apiRequest(`${SKILLS_API_PREFIX}/${skillId}/trust`, {
    method: 'POST',
  });
}

export async function untrustSkill(skillId: string): Promise<{ skill_id: string; trust: string }> {
  return apiRequest(`${SKILLS_API_PREFIX}/${skillId}/trust`, {
    method: 'DELETE',
  });
}

export async function toggleEvolutionLock(
  skillId: string,
  locked: boolean,
): Promise<{ skill_id: string; evolution_locked: boolean }> {
  return apiRequest(`${SKILLS_API_PREFIX}/${skillId}/evolution-lock?locked=${locked}`, { method: 'POST' });
}

// ========== Skill Drafts API (Background Review) ==========

export interface SkillDraft {
  id: string;
  agent_id: string;
  chat_id: string | null;
  draft_type: string;
  name: string | null;
  description: string | null;
  trigger_condition: string | null;
  skill_steps: string | null;
  content: string | null;
  status: 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'FAILED_SCAN' | 'AUTO_APPLIED' | 'BLOCKED_LOCKED';
  reviewed_at: string | null;
  created_at: string;
}

export interface SkillDraftListResponse {
  drafts: SkillDraft[];
  total: number;
}

export interface UnreviewedCountResponse {
  unreviewed_count: number;
}

export async function listSkillDrafts(
  status?: 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED',
  limit: number = 50,
  offset: number = 0,
): Promise<SkillDraftListResponse> {
  const params = new URLSearchParams();
  if (status) {
    params.append('status', status);
  }
  params.append('limit', String(limit));
  params.append('offset', String(offset));
  return apiRequest<SkillDraftListResponse>(`${SKILLS_API_PREFIX}/drafts?${params}`);
}

export async function getSkillDraft(draftId: string): Promise<SkillDraft> {
  return apiRequest<SkillDraft>(`${SKILLS_API_PREFIX}/drafts/${draftId}`);
}

export async function getUnreviewedDraftCount(): Promise<UnreviewedCountResponse> {
  return apiRequest<UnreviewedCountResponse>(`${SKILLS_API_PREFIX}/drafts/unreviewed/count`);
}

export interface ApproveDraftResult {
  id: string;
  status: string;
  materialized?: boolean;
  materialized_type?: 'skill' | 'memory';
  skill_name?: string;
  saved_path?: string;
  memory_id?: string;
  error?: string;
}

export async function approveSkillDraft(
  draftId: string,
  skillName?: string,
  scopeAgentId?: string,
): Promise<ApproveDraftResult> {
  return apiRequest<ApproveDraftResult>(`${SKILLS_API_PREFIX}/drafts/${draftId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ skill_name: skillName, scope_agent_id: scopeAgentId }),
  });
}

export async function rejectSkillDraft(draftId: string): Promise<{ id: string; status: string }> {
  return apiRequest(`${SKILLS_API_PREFIX}/drafts/${draftId}/reject`, { method: 'POST' });
}

// ========== Curator API ==========

export interface LifecycleActionResponse {
  skill_name: string;
  action: string;
  new_status: SkillLifecycleStatus;
  pinned: boolean;
}

export interface CuratorConfigResponse {
  enabled: boolean;
  interval_hours: number;
  stale_after_days: number;
  archive_after_days: number;
  grace_period_days: number;
  min_success_rate: number;
  max_skills: number;
  protect_installed_skills: boolean;
  consolidation_enabled: boolean;
  consolidation_min_cluster_size: number;
  consolidation_similarity_threshold: number;
}

export interface CuratorRunResponse {
  skills_scanned: number;
  total_transitions: number;
  stale_count: number;
  archived_count: number;
  skipped_pinned: number;
  transitions: Array<{
    skill_name: string;
    from_status: string;
    to_status: string;
    reason: string;
  }>;
}

export async function updateSkillLifecycle(
  skillName: string,
  action: SkillLifecycleAction,
): Promise<LifecycleActionResponse> {
  return apiRequest<LifecycleActionResponse>(`${SKILLS_API_PREFIX}/curator/${skillName}/lifecycle`, {
    method: 'PATCH',
    body: JSON.stringify({ action }),
  });
}

export async function getCuratorConfig(): Promise<CuratorConfigResponse> {
  return apiRequest<CuratorConfigResponse>(`${SKILLS_API_PREFIX}/curator/config`);
}

export async function updateCuratorConfig(updates: Partial<CuratorConfigResponse>): Promise<CuratorConfigResponse> {
  return apiRequest<CuratorConfigResponse>(`${SKILLS_API_PREFIX}/curator/config`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function runCuratorSweep(): Promise<CuratorRunResponse> {
  return apiRequest<CuratorRunResponse>(`${SKILLS_API_PREFIX}/curator/run`, {
    method: 'POST',
  });
}

export interface CuratorHistoryEntry {
  timestamp: string;
  trigger: 'manual' | 'background';
  duration_ms: number;
  skills_scanned: number;
  total_transitions: number;
  stale_count: number;
  archived_count: number;
  skipped_pinned: number;
  transitions: Array<{
    skill_name: string;
    from_status: string;
    to_status: string;
    reason: string;
  }>;
  errors: string[];
}

export async function getCuratorHistory(limit: number = 10): Promise<CuratorHistoryEntry[]> {
  return apiRequest<CuratorHistoryEntry[]>(`${SKILLS_API_PREFIX}/curator/history?limit=${limit}`);
}

// --- Skill Health Doctor Diagnostics API ---

export interface SkillDoctorFindingItem {
  skill_name: string;
  finding_type: 'wrong_but_frequent' | 'hoarding_bloat' | 'stale_pinned';
  severity: 'critical' | 'warning' | 'info';
  message: string;
  call_count: number;
  success_rate: number;
  pinned: boolean;
  recommended_action: 'unpin_and_archive' | 'archive' | 'reset_stats' | 'evolve';
  details: Record<string, unknown>;
}

export interface SkillDoctorDiagnosticsResponse {
  total_skills: number;
  active_skills: number;
  stale_skills: number;
  archived_skills: number;
  pinned_skills: number;
  findings: SkillDoctorFindingItem[];
  health_score: number;
}

export interface SkillRemediationResponse {
  success: boolean;
  skill_name?: string;
  action?: string;
  new_status?: string;
  pinned?: boolean;
  call_count?: number;
  error?: string;
}

export async function getSkillDiagnostics(): Promise<SkillDoctorDiagnosticsResponse> {
  return apiRequest<SkillDoctorDiagnosticsResponse>(`${SKILLS_API_PREFIX}/curator/diagnostics`);
}

export async function remediateSkillFinding(
  skillName: string,
  action: 'unpin_and_archive' | 'archive' | 'reset_stats',
): Promise<SkillRemediationResponse> {
  return apiRequest<SkillRemediationResponse>(`${SKILLS_API_PREFIX}/curator/remediate`, {
    method: 'POST',
    body: JSON.stringify({ skill_name: skillName, action }),
  });
}

// --- Consolidation (Umbrella Merge) API ---

export interface ConsolidationAction {
  action_type: string;
  target_skill: string;
  source_skills: string[];
  reasoning: string;
}

export interface ConsolidationPreviewResponse {
  actions: ConsolidationAction[];
  total_skills_affected: number;
  estimated_reduction: number;
  preview_summary: string;
}

export interface ConsolidationExecuteResponse {
  success_count: number;
  failure_count: number;
  total_archived: number;
  total_created: number;
  net_reduction: number;
  summary: string;
  agent_refs_updated: number;
}

export async function getConsolidationPreview(): Promise<ConsolidationPreviewResponse> {
  return apiRequest<ConsolidationPreviewResponse>(`${SKILLS_API_PREFIX}/curator/consolidation/preview`, {
    method: 'POST',
  });
}

export async function executeConsolidation(): Promise<ConsolidationExecuteResponse> {
  return apiRequest<ConsolidationExecuteResponse>(`${SKILLS_API_PREFIX}/curator/consolidation/execute`, {
    method: 'POST',
  });
}

// --- Collective Skill Sync ---

export interface SkillSyncStatus {
  enabled: boolean;
  last_sync_at: string | null;
  pending_push_count: number;
  pending_pull_count: number;
  is_syncing: boolean;
}

export interface SkillSyncTriggerResult {
  success: boolean;
  push_count: number;
  pull_new: number;
  pull_updated: number;
  error: string;
}

export async function getSkillSyncStatus(): Promise<SkillSyncStatus> {
  return apiRequest<SkillSyncStatus>(`${SKILLS_API_PREFIX}/sync/status`);
}

export async function triggerSkillSync(): Promise<SkillSyncTriggerResult> {
  return apiRequest<SkillSyncTriggerResult>(`${SKILLS_API_PREFIX}/sync/trigger`, {
    method: 'POST',
  });
}

// --- Prebuilt Skill Update Management ---

interface PrebuiltActionResult {
  status: string;
  message: string;
}

export async function resetPrebuiltToDefault(skillId: string): Promise<PrebuiltActionResult> {
  return apiRequest<PrebuiltActionResult>(`${SKILLS_API_PREFIX}/${skillId}/reset-to-default`, {
    method: 'POST',
  });
}

export async function acceptPrebuiltUpstream(skillId: string): Promise<PrebuiltActionResult> {
  return apiRequest<PrebuiltActionResult>(`${SKILLS_API_PREFIX}/${skillId}/accept-upstream`, {
    method: 'POST',
  });
}

// --- Custom Skill Sources ---

export interface CustomSource {
  url: string;
  source_type: string;
  label: string;
  healthy: boolean;
}

export interface CustomSourceListResponse {
  sources: CustomSource[];
}

export interface CustomSourceProbeResponse {
  reachable: boolean;
  skill_count: number;
  url: string;
}

export async function getCustomSources(): Promise<CustomSourceListResponse> {
  return apiRequest<CustomSourceListResponse>(`${SKILLS_API_PREFIX}/discovery/sources`);
}

export async function addCustomSource(
  url: string,
  sourceType: string = 'well-known',
  label: string = '',
): Promise<CustomSourceProbeResponse> {
  return apiRequest<CustomSourceProbeResponse>(`${SKILLS_API_PREFIX}/discovery/sources`, {
    method: 'POST',
    body: JSON.stringify({ url, source_type: sourceType, label }),
  });
}

export async function removeCustomSource(url: string): Promise<{ removed: boolean }> {
  return apiRequest<{ removed: boolean }>(`${SKILLS_API_PREFIX}/discovery/sources?url=${encodeURIComponent(url)}`, {
    method: 'DELETE',
  });
}

// --- Skill Pool Cross-Agent Sync ---

export interface SkillPoolSyncResponse {
  success: boolean;
  skill_id: string;
  synced_agents: string[];
  failed_agents: string[];
}

export async function syncSkillPoolToAgents(skillId: string, targetAgentIds: string[]): Promise<SkillPoolSyncResponse> {
  return apiRequest<SkillPoolSyncResponse>(`${SKILLS_API_PREFIX}/discovery/pool/sync`, {
    method: 'POST',
    body: JSON.stringify({
      skill_id: skillId,
      target_agent_ids: targetAgentIds,
    }),
  });
}

// --- Desktop Workflow Skill Recorder ---

export interface WorkflowPlanStep {
  step_id: string;
  title: string;
  description: string;
  tool_hint?: string;
  target_app?: string;
  variables_used?: string[];
}

export interface WorkflowIntentPlan {
  name: string;
  description?: string;
  intent?: string;
  steps: WorkflowPlanStep[];
  variables?: Record<string, string>;
  allowed_tools?: string[];
}

export interface AnalyzeDesktopPlanResponse {
  plan: WorkflowIntentPlan;
  event_count: number;
  validation_errors: string[];
}

export interface CompileDesktopPlanResponse {
  markdown_content: string;
  validation_errors: string[];
}

export interface PublishDesktopSkillResponse {
  skill_id: string;
  skill_name: string;
  status: string;
  file_path: string;
}

export async function startDesktopRecording(
  sessionId: string,
  appScope: string = 'all',
): Promise<{ session_id: string; status: string; started_at: number }> {
  return apiRequest(`${SKILLS_API_PREFIX}/desktop-recorder/start`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, app_scope: appScope }),
  });
}

export async function stopDesktopRecording(
  sessionId: string,
): Promise<{ session_id: string; status: string; event_count: number; duration_seconds: number }> {
  return apiRequest(`${SKILLS_API_PREFIX}/desktop-recorder/stop`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export async function recordDesktopEvent(payload: {
  session_id: string;
  seq: number;
  action: string;
  app_name?: string;
  window_title?: string;
  element_title?: string;
  value?: string;
}): Promise<{ status: string; recorded_count: number }> {
  return apiRequest(`${SKILLS_API_PREFIX}/desktop-recorder/event`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function analyzeDesktopPlan(
  sessionId: string,
  skillName: string = 'desktop-workflow-skill',
  intentHint: string = '',
): Promise<AnalyzeDesktopPlanResponse> {
  return apiRequest<AnalyzeDesktopPlanResponse>(`${SKILLS_API_PREFIX}/desktop-recorder/analyze-plan`, {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, skill_name: skillName, intent_hint: intentHint }),
  });
}

export async function compileDesktopPlan(plan: WorkflowIntentPlan): Promise<CompileDesktopPlanResponse> {
  return apiRequest<CompileDesktopPlanResponse>(`${SKILLS_API_PREFIX}/desktop-recorder/compile-plan`, {
    method: 'POST',
    body: JSON.stringify({ plan }),
  });
}

export async function publishDesktopSkill(
  sessionId: string,
  skillName: string,
  markdownContent: string,
  description: string = '',
): Promise<PublishDesktopSkillResponse> {
  return apiRequest<PublishDesktopSkillResponse>(`${SKILLS_API_PREFIX}/desktop-recorder/publish`, {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      skill_name: skillName,
      markdown_content: markdownContent,
      description,
    }),
  });
}
