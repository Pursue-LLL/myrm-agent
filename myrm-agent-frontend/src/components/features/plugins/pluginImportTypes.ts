/**
 * Wire types of the plugin import API (`/api/v1/plugins/import/*`) and the pure rules the
 * import dialog derives from them (what is blocked, what is preselected).
 */

export interface CapabilityDiff {
  added: string[];
  removed: string[];
  has_escalation: boolean;
}

export interface PluginMeta {
  name: string;
  version: string | null;
  description: string | null;
  author: Record<string, string> | null;
  homepage: string | null;
  repository: string | null;
  license: string | null;
  keywords: string[];
  capabilities: string[];
  effective_tier: string;
  risk_level: string;
  capability_diff: CapabilityDiff | null;
}

export interface PluginSkillPreview {
  name: string;
  description: string;
  file_count: number;
  virtual_id: string;
  security_issues: string[];
  oversized_content: boolean;
  /** Machine code: why this deployment cannot install the skill. */
  blocked_reason: string | null;
  conflict: boolean;
  existing_version: string | null;
  existing_source: string | null;
}

export interface PluginServerPreview {
  name: string;
  type: string;
  command: string | null;
  url: string | null;
  env_key_count: number;
  has_placeholders: boolean;
  virtual_id: string;
  missing_artifact: string | null;
  is_runnable: boolean;
  missing_artifacts: string[];
  capabilities: string[];
  /** Machine code: why this deployment cannot use the connector. */
  blocked_reason: string | null;
}

export interface PluginAgentPreview {
  name: string;
  description: string;
  system_prompt: string;
  max_iterations: number | null;
  effective_max_iterations: number | null;
  skill_names: string[];
  tool_names: string[];
  /** Requested tools that will be enabled. */
  granted_tools: string[];
  /** Requested tools left for the user to enable. */
  withheld_tools: string[];
  /** The author's model hint; shown, never applied. */
  recommended_model: string | null;
  ignored_declarations: string[];
  mcp_names: string[];
  subagent_names: string[];
  is_subagent: boolean;
  is_entry_agent: boolean;
  virtual_id: string;
  /** An expert with the same name already exists. */
  conflict: boolean;
  existing_agent_id: string | null;
  existing_is_built_in: boolean;
  unresolved_skills: string[];
  unresolved_connectors: string[];
  unresolved_subagents: string[];
}

export interface PluginDiagnostic {
  component: string;
  code: string;
  message: string;
  level: string;
}

export interface PluginDeploymentFlags {
  allows_local_skills: boolean;
  allow_stdio: boolean;
}

export interface PluginPreviewPayload {
  session_id: string;
  plugin: PluginMeta;
  skills: PluginSkillPreview[];
  servers: PluginServerPreview[];
  agents: PluginAgentPreview[];
  workspace_file_count: number;
  deployment: PluginDeploymentFlags;
  diagnostics: PluginDiagnostic[];
  is_valid: boolean;
}

export interface PluginAgentResult {
  agent_id: string;
  package_name: string;
  stored_name: string;
  action: 'created' | 'replaced';
  previous_version_saved: boolean;
  withheld_tools: string[];
  unresolved_skills: string[];
  unresolved_connectors: string[];
  unresolved_subagents: string[];
}

export interface PluginComponentFailure {
  component: 'skill' | 'mcp' | 'agent';
  name: string;
  /** Machine code, localized by the client. */
  code: string;
  message: string;
}

export interface PluginConfirmResult {
  imported_skills: number;
  skipped_skills: number;
  imported_servers: number;
  skipped_servers: number;
  imported_agents: number;
  skipped_agents: number;
  required_secret_keys: string[];
  created_agent_ids: string[];
  agents: PluginAgentResult[];
  failures: PluginComponentFailure[];
}

export type Resolution = 'install' | 'replace' | 'skip';

export interface ComponentDecision {
  virtual_id: string;
  name: string;
  resolution: Resolution;
}

export interface ImportDecisions {
  skills: ComponentDecision[];
  servers: ComponentDecision[];
  agents: ComponentDecision[];
}

export type ComponentKind = keyof ImportDecisions;

export function isSkillBlocked(item: PluginSkillPreview): boolean {
  return item.security_issues.length > 0 || item.oversized_content || Boolean(item.blocked_reason);
}

export function isServerBlocked(item: PluginServerPreview): boolean {
  return Boolean(item.missing_artifact) || item.is_runnable === false || Boolean(item.blocked_reason);
}

/**
 * Safe starting point: blocked components are skipped and a same-name skill is never overwritten
 * unless the user asks; experts import as non-destructive copies.
 */
export function defaultDecisions(preview: PluginPreviewPayload): ImportDecisions {
  const decide = (virtualId: string, name: string, skipped: boolean): ComponentDecision => ({
    virtual_id: virtualId,
    name,
    resolution: skipped ? 'skip' : 'install',
  });

  return {
    skills: preview.skills.map((item) => decide(item.virtual_id, item.name, isSkillBlocked(item) || item.conflict)),
    servers: preview.servers.map((item) => decide(item.virtual_id, item.name, isServerBlocked(item))),
    agents: preview.agents.map((item) => decide(item.virtual_id, item.name, false)),
  };
}

/** What a bulk "select all" / "skip all" does to one component, honoring what must stay skipped. */
export function bulkResolution(
  kind: ComponentKind,
  preview: PluginPreviewPayload,
  decision: ComponentDecision,
  target: 'install' | 'skip',
): Resolution {
  if (target === 'skip') {
    return 'skip';
  }
  if (kind === 'skills') {
    const skill = preview.skills.find((item) => item.virtual_id === decision.virtual_id);
    if (skill && isSkillBlocked(skill)) {
      return decision.resolution;
    }
    // A same-name skill is upgraded in place, never duplicated.
    return skill?.conflict ? 'replace' : 'install';
  }
  if (kind === 'servers') {
    const server = preview.servers.find((item) => item.virtual_id === decision.virtual_id);
    return server && isServerBlocked(server) ? 'skip' : 'install';
  }
  return 'install';
}

export function countSelected(decisions: ComponentDecision[]): number {
  return decisions.filter((item) => item.resolution !== 'skip').length;
}
