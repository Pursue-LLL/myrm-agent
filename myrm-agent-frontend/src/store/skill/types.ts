/**
 * Skill system type definitions
 */

export type SkillType = 'prebuilt' | 'local' | 'workspace';

export type SkillLifecycleStatus = 'active' | 'stale' | 'archived';
export type SkillLifecycleAction = 'pin' | 'unpin' | 'restore' | 'archive' | 'reset-to-default' | 'accept-upstream';

export type SkillCategory =
  | 'development'
  | 'research'
  | 'creative'
  | 'productivity'
  | 'pipeline'
  | 'data'
  | 'social-media'
  | 'media'
  | 'mlops'
  | 'workflow'
  | 'data-science'
  | 'data-collection'
  | 'other';

export interface SkillRequires {
  bins: string[];
  env: string[];
  config: string[];
}

export interface SecurityFinding {
  threat_type: string;
  severity: string;
  description: string;
}

export interface SecurityScanSummary {
  score: number;
  trust_recommendation: string;
  finding_counts: Record<string, number>;
  total_findings: number;
  findings: SecurityFinding[];
}

export interface SkillTrap {
  description: string;
  severity: string;
  trigger_condition: string;
  mitigation: string;
  occurrence_count: number;
}

export interface SkillVerificationStep {
  step_id: string;
  description: string;
  expected_output: string;
  validation_method: string;
}

export interface Skill {
  id: string;
  type: SkillType;
  name: string;
  description: string;
  storage_path: string;
  version: string;
  category: SkillCategory | string | null;
  icon_url: string | null;
  tags: string[];
  is_active: boolean;
  token_cost?: number | null;

  requires: SkillRequires;
  available: boolean;
  unavailable_reason: string | null;

  trust: string;
  author: string | null;
  homepage: string | null;
  always: boolean;

  /** Whether the model can auto-select this skill */
  model_invocable: boolean;
  /** Whether the user can manually trigger this skill */
  user_invocable: boolean;

  /** Declared primary env var name for apiKey mapping (from SKILL.md frontmatter) */
  primary_env: string | null;

  /** Required permissions (from SKILL.md frontmatter) */
  required_permissions?: string[];
  missing_credentials?: string[];

  /** Allowed domains for outbound network requests (DLP protection) */
  allowed_domains?: string[] | null;

  security: SecurityScanSummary | null;
  user_trusted: boolean;

  evolution_locked: boolean;
  scope_agent_id?: string | null;

  /** JSON Schema for skill configuration (from SKILL.md frontmatter) */
  config_schema?: Record<string, unknown> | null;

  /** True when upstream has a newer version but user modifications were preserved */
  has_upstream_update: boolean;

  usage_stats?: {
    call_count: number;
    success_count: number;
    failure_count: number;
    last_used_at: string | null;
    total_duration_ms: number;
    success_rate: number;
    avg_duration_ms: number;
    lifecycle_status: SkillLifecycleStatus;
    pinned: boolean;
  } | null;

  traps: SkillTrap[];
  verification_steps: SkillVerificationStep[];

  created_at: string;
  updated_at: string;
}

export interface SkillListResponse {
  skills: Skill[];
  total: number;
}

export interface UserSkillConfig {
  user_id: string;
  enabled_prebuilt_ids: string[];
  disabled_prebuilt_ids?: string[];
  local_skill_paths: string[];
  enabled_local_skill_ids: string[];
  evolution_strategy?: string;
  updated_at: string;
}

export interface LocalSkillPathsResponse {
  paths: string[];
  default_paths: string[];
}

export interface UpdateUserSkillConfigRequest {
  enabled_prebuilt_ids?: string[];
  evolution_strategy?: string;
}

export type SkillSortBy = 'name' | 'created_at' | 'updated_at' | 'token_cost';
export type SkillSortOrder = 'asc' | 'desc';

export interface SkillFilters {
  search: string;
  category: string | null;
  tags: string[];
  sortBy: SkillSortBy;
  sortOrder: SkillSortOrder;
}

/** Source filter for installed tab */
export type SkillSourceFilter = 'all' | 'prebuilt' | 'local' | 'workspace';

/** Status filter for installed tab */
export type SkillStatusFilter = 'all' | 'ready' | 'needs-setup' | 'disabled' | 'stale' | 'archived';

export interface SkillState {
  isSandboxMode: boolean;
  marketSkills: Skill[];
  localSkills: Skill[];
  enabledPrebuiltIds: string[];
  localSkillPaths: string[];
  enabledLocalSkillIds: string[];
  defaultLocalPaths: string[];
  evolutionStrategy: string;

  isLoadingMarket: boolean;
  isLoadingLocal: boolean;
  isLoadingConfig: boolean;

  filters: SkillFilters;
  error: string | null;
  lastFetchedConfigUserId: string | null;
}

export interface SkillActions {
  fetchMarketSkills: (forceRefresh?: boolean) => Promise<void>;
  fetchUserSkillConfig: (forceRefresh?: boolean) => Promise<void>;
  fetchLocalSkills: () => Promise<void>;
  fetchLocalSkillPaths: () => Promise<void>;

  enableSkill: (skillId: string, force?: boolean) => Promise<void>;
  disableSkill: (skillId: string) => Promise<void>;
  toggleSkill: (skillId: string) => Promise<void>;

  updateLocalSkillPaths: (paths: string[]) => Promise<void>;
  addLocalSkillPath: (path: string) => Promise<void>;
  removeLocalSkillPath: (path: string) => Promise<void>;
  updateEvolutionStrategy: (strategy: string) => Promise<void>;
  scanLocalSkills: () => Promise<void>;
  toggleLocalSkill: (skillId: string) => Promise<void>;

  /** Batch enable/disable multiple skills */
  batchToggleSkills: (skillIds: string[], enable: boolean) => Promise<void>;

  setFilters: (filters: Partial<SkillFilters>) => void;
  clearFilters: () => void;

  isSkillEnabled: (skillId: string) => boolean;
  getFilteredMarketSkills: () => Skill[];
  getFilteredLocalSkills: () => Skill[];
  getAllTags: () => string[];

  reset: () => void;
}

export type SkillStore = SkillState & SkillActions;

export interface CreateCustomSkillRequest {
  name: string;
  description: string;
  category?: string;
  tags?: string;
  files: globalThis.File[];
}

/**
 * Skill permission approval error
 * 当Skill需要权限审批时抛出此错误
 */
export class SkillPermissionRequiredError extends Error {
  constructor(
    public skillId: string,
    public skillName: string,
    public requiredPermissions: string[],
    public description: string = '',
  ) {
    super(`Skill ${skillName} requires permission approval`);
    this.name = 'SkillPermissionRequiredError';
  }
}

/**
 * Skill blocked by security scan error
 * 当Skill因安全扫描发现威胁被阻止时抛出此错误
 */
export interface ScanFinding {
  threat_type: string;
  severity: number;
  description: string;
  line_number: number | null;
}

export class SkillBlockedError extends Error {
  constructor(
    public skillId: string,
    public skillName: string,
    public scanFindings: ScanFinding[],
  ) {
    super(`Skill ${skillName} blocked by security scan: ${scanFindings.length} finding(s)`);
    this.name = 'SkillBlockedError';
  }
}
