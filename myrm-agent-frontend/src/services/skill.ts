/**
 * 技能 API 服务
 */

import { apiRequest } from '@/lib/api';
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
  if (type) queryParams.append('type', type);
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
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1'}${SKILLS_API_PREFIX}/${skillId}/files/${filename}`,
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch skill file: ${response.statusText}`);
  }

  return response.text();
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
 */
export async function downloadSkill(
  skillId: string, 
  applyRedactions: boolean = false,
  ignoredRedactions: Record<string, number[]> = {}
): Promise<Blob> {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1';

  const response = await fetch(`${API_BASE}${SKILLS_API_PREFIX}/${skillId}/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('auth_token') || ''}`,
    },
    body: JSON.stringify({
      apply_redactions: applyRedactions,
      ignored_redactions: ignoredRedactions,
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`下载失败: ${error}`);
  }

  return response.blob();
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

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1';

  const response = await fetch(`${API_BASE}/storage/workspace/package`, {
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

/**
 * 触发浏览器下载 Blob
 * @param blob 文件内容
 * @param filename 文件名
 */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
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
  error: string;
}

export interface DiscoveryPreviewResponse {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  files: string[];
  scan_findings: ScanFinding[];
  is_clean: boolean;
}

export async function searchDiscoverySkills(
  query: string,
  limit: number = 30,
  userId?: string,
): Promise<DiscoverySearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (userId) params.set('user_id', userId);
  return apiRequest<DiscoverySearchResponse>(`${SKILLS_API_PREFIX}/discovery/search?${params}`);
}

export async function previewDiscoverySkill(skillId: string, source: string): Promise<DiscoveryPreviewResponse> {
  return apiRequest<DiscoveryPreviewResponse>(`${SKILLS_API_PREFIX}/discovery/preview`, {
    method: 'POST',
    body: JSON.stringify({ skill_id: skillId, source }),
  });
}

export async function installDiscoverySkill(skillId: string, source: string): Promise<DiscoveryInstallResponse> {
  return apiRequest<DiscoveryInstallResponse>(`${SKILLS_API_PREFIX}/discovery/install`, {
    method: 'POST',
    body: JSON.stringify({ skill_id: skillId, source }),
  });
}

export async function uninstallDiscoverySkill(skillId: string): Promise<DiscoveryInstallResponse> {
  return apiRequest<DiscoveryInstallResponse>(`${SKILLS_API_PREFIX}/discovery/uninstall`, {
    method: 'POST',
    body: JSON.stringify({ skill_id: skillId }),
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
    body: JSON.stringify({ url }),
  });
}

export async function installDiscoverySkillFromUrl(url: string): Promise<DiscoveryInstallResponse> {
  return apiRequest<DiscoveryInstallResponse>(`${SKILLS_API_PREFIX}/discovery/install-from-url`, {
    method: 'POST',
    body: JSON.stringify({ url }),
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
  if (status) params.append('status', status);
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

export async function approveSkillDraft(draftId: string, skillName?: string): Promise<ApproveDraftResult> {
  return apiRequest<ApproveDraftResult>(`${SKILLS_API_PREFIX}/drafts/${draftId}/approve`, {
    method: 'POST',
    body: JSON.stringify({ skill_name: skillName }),
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
