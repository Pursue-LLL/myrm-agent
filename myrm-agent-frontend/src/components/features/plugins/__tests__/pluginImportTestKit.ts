/**
 * Shared fixtures and a namespace-aware `next-intl` stand-in for the plugin import tests.
 * Payload builders produce complete API bodies, so tests only state what they care about.
 */
import type {
  PluginAgentPreview,
  PluginConfirmResult,
  PluginPreviewPayload,
  PluginServerPreview,
  PluginSkillPreview,
} from '../pluginImportTypes';

const IMPORT_NAMESPACE = 'settings.plugins.import';

// Keys are relative to `settings.plugins.import`; sub-namespaces (`security`, `result`, ...) are part of the key.
const IMPORT_TEXT: Record<string, string> = {
  title: 'Import Plugin',
  subtitle: 'Install an agent plugin package',
  'upload.dropHint': 'Drop your plugin ZIP here',
  'upload.parsing': 'Parsing...',
  'upload.formatHint': 'Accepts .zip archives',
  'upload.archiveOnly': 'Only .zip archives are supported',
  'upload.singleArchiveOnly': 'Only a single archive is allowed',
  'upload.tooLarge': 'Archive exceeds the 20MB limit',
  'errors.previewFailed': 'Preview failed',
  'errors.requestFailed': 'Request failed',
  'errors.sessionExpired': 'Session expired',
  'errors.confirmFailed': 'Confirm failed',
  'errors.parseTitle': 'Parse error',
  'errors.confirmTitle': 'Confirm error',
  'actions.reselect': 'Reselect',
  'actions.cancel': 'Cancel',
  'actions.confirm': 'Import',
  'actions.install': 'Install',
  'actions.replace': 'Replace',
  'actions.skip': 'Skip',
  'actions.importCopy': 'Import as copy',
  'actions.importAnother': 'Import another',
  'actions.done': 'Done',
  'actions.selectAll': 'Select all',
  'actions.skipAll': 'Skip all',
  'bind.label': 'Bind to agent',
  'bind.placeholder': 'Select an agent',
  'bind.hint': 'The selected agent will receive the MCP servers.',
  'success.title': 'Import complete',
  'success.description': 'Imported {agents} agents, {skills} skills and {servers} servers',
  'success.requiredKeys': 'Configure these keys: {keys}',
  'success.disabledHint': 'Imported MCP servers are disabled by default',
  summary: 'Summary {agents}/{skills}/{servers}',
  'sections.agents': 'Agents ({count})',
  'sections.skills': 'Skills',
  'sections.servers': 'MCP Servers',
  'sections.files': 'files',
  'sections.placeholder': 'needs config',
  'sections.workspaceFiles': 'Workspace Assets ({count})',
  'sections.envCount': '{count} env vars',
  'agents.entry': 'Entry Agent',
  'agents.subagent': 'Subagent',
  'agents.skillsCount': '{count} skill(s)',
  'agents.toolsCount': '{count} tool(s)',
  'agents.subagentsCount': '{count} subagent(s)',
  'agents.templateFiles': '{count} template file(s)',
  'agents.conflict': 'An agent with this name already exists',
  'agents.conflictBuiltIn': 'A built-in agent has this name',
  'agents.withheldTools': 'Left off: {tools}',
  'agents.unresolvedSkills': 'Skills not available: {names}',
  'agents.unresolvedConnectors': 'MCP servers not available: {names}',
  'agents.unresolvedSubagents': 'Sub-agents missing: {names}',
  'agents.iterationsCapped': 'Loop limit lowered from {requested} to {effective}',
  'agents.recommendedModel': 'Written for {model}',
  'agents.ignoredDeclarations': 'Not used: {names}',
  'skills.installedVersion': 'Installed version: {version}',
  'empty.title': 'No importable components',
  'empty.hint': 'Check the diagnostics',
  'serverType.local': 'Local process',
  'serverType.remote': 'Remote service',
  'diagnostics.scope.plugin': 'Plugin package',
  'diagnostics.scope.skill': 'Skill: {name}',
  'diagnostics.scope.servers': 'MCP servers',
  'diagnostics.scope.server': 'MCP server: {name}',
  'diagnostics.messages.unsupportedFormat': 'This is not a supported plugin package',
  'diagnostics.messages.manifestInvalid': 'The description file is invalid',
  'diagnostics.messages.serversInvalid': 'The MCP server settings are invalid',
  'diagnostics.messages.skillSkipped': 'This skill was skipped',
  'diagnostics.messages.serverSkipped': 'This MCP server was skipped',
  'diagnostics.messages.filesIgnored': 'Hidden files were not imported',
  'diagnostics.messages.generic': 'This plugin has an issue that may affect the import',
  'deployment.noLocalSkills': 'Custom skills cannot be installed here',
  'deployment.noLocalConnectors': 'Local MCP servers cannot run here',
  'security.blocked': 'Blocked: {count} security risk(s) found — automatically skipped',
  'security.oversized': 'Skill content exceeds the storage size limit (64 KB) — automatically skipped',
  'security.conflict': 'A skill with this name already exists — Replace upgrades it, or Skip to keep the current one',
  'security.skillsNotSupported': 'This environment does not allow custom skills',
  'security.stdioNotAllowed': 'Local-process MCP servers cannot run in this environment',
  'security.missingArtifact': 'Missing build artifact: {file}',
  'security.trustDisclosureTitle': 'Trusted Source & System Permissions Security Disclosure',
  'security.trustDisclosureLocal': 'Running in Local/Desktop mode. Full host OS permissions.',
  'security.trustDisclosureCloud': 'Running in Cloud Sandbox mode. Dedicated isolated volume.',
  'security.trustRiskHint': 'Untrusted extensions may contain prompt injection.',
  'security.trustedCheckboxLabel': 'I confirm this plugin is from a trusted source',
  'capabilities.title': 'Sandbox Capabilities',
  'capabilities.read_only': 'Read-Only',
  'capabilities.fs_read': 'File Read',
  'capabilities.fs_write': 'File Write',
  'capabilities.network': 'Network Outbound',
  'capabilities.shell_exec': 'Shell Exec',
  'capabilities.destructive': 'Destructive / System',
  'capabilities.risk.low': 'Low Risk',
  'capabilities.risk.medium': 'Medium Risk',
  'capabilities.risk.high': 'High Risk',
  'capabilities.risk.critical': 'Critical Risk',
  'capabilities.undeclaredWarning':
    'Undeclared capability detected: this service requires permissions beyond what was declared in plugin.json.',
  'capabilities.escalationTitle': 'Privilege Escalation Risk Detected',
  'capabilities.escalationWarning':
    'This version requests elevated system permissions compared to previous installation: added [{added}]. Please verify the plugin source before confirming.',
  'failures.title': 'Some components were not imported',
  'failures.components.skill': 'Skill',
  'failures.components.mcp': 'MCP server',
  'failures.components.agent': 'Agent',
  'failures.codes.install_failed': 'The skill could not be installed',
  'failures.codes.stdio_not_allowed': 'Local MCP servers cannot run here',
  'failures.codes.generic': 'It could not be imported',
  'result.checking': 'Checking readiness...',
  'result.readinessUnavailable': 'Readiness could not be checked',
  'result.allReady': 'Ready to use',
  'result.created': 'New',
  'result.replaced': 'Replaced',
  'result.renamedFrom': 'Imported from "{name}"',
  'result.previousVersionSaved': 'The previous version was saved',
  'result.openAgent': 'Open agent',
  'result.withheldTools': 'Left off: {tools}',
  'result.unresolvedSkills': 'Skills not available: {names}',
  'result.unresolvedConnectors': 'MCP servers not available: {names}',
  'result.unresolvedSubagents': 'Sub-agents missing: {names}',
};

const TEXT: Record<string, string> = {
  ...Object.fromEntries(Object.entries(IMPORT_TEXT).map(([key, value]) => [`${IMPORT_NAMESPACE}.${key}`, value])),
  'Agent.readiness.dimensions.model': 'Model',
  'Agent.readiness.dimensions.mcp': 'MCP servers',
  'Agent.readiness.dimensions.other': 'Other',
  'Agent.readiness.reasons.model_not_ready': 'No model is ready yet',
  'Agent.readiness.fallback.warning': 'This may limit the agent',
  'Agent.readiness.fallback.blocked': 'This needs attention',
  'Agent.readiness.fix': 'Fix',
  // Archive-security refusals reuse the skills import wording.
  'settings.skills.batchImport.errors.archiveSecurity.executableBinaryDetected': 'Blocked: executable binary',
};

export function translate(fullKey: string, values?: Record<string, unknown>): string {
  let text = TEXT[fullKey] ?? fullKey;
  for (const [name, value] of Object.entries(values ?? {})) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

/** Drop-in for `useTranslations(namespace)`: resolves `${namespace}.${key}` against the texts above. */
export function useTranslationsStub(namespace?: string) {
  const fullKey = (key: string) => (namespace ? `${namespace}.${key}` : key);
  return Object.assign((key: string, values?: Record<string, unknown>): string => translate(fullKey(key), values), {
    has: (key: string): boolean => fullKey(key) in TEXT,
  });
}

export function skillPreview(overrides: Partial<PluginSkillPreview> = {}): PluginSkillPreview {
  return {
    name: 'summarize',
    description: 'Summarize a PDF',
    file_count: 1,
    virtual_id: 'skill:0',
    security_issues: [],
    oversized_content: false,
    blocked_reason: null,
    conflict: false,
    existing_version: null,
    existing_source: null,
    ...overrides,
  };
}

export function serverPreview(overrides: Partial<PluginServerPreview> = {}): PluginServerPreview {
  return {
    name: 'pdf-server',
    type: 'stdio',
    command: './bin/pdf',
    url: null,
    env_key_count: 0,
    has_placeholders: false,
    virtual_id: 'mcp:0',
    missing_artifact: null,
    is_runnable: true,
    missing_artifacts: [],
    capabilities: [],
    blocked_reason: null,
    ...overrides,
  };
}

export function agentPreview(overrides: Partial<PluginAgentPreview> = {}): PluginAgentPreview {
  return {
    name: 'Report Lead',
    description: 'Coordinates the report team',
    system_prompt: 'You lead the report team.',
    max_iterations: null,
    effective_max_iterations: null,
    skill_names: [],
    tool_names: [],
    granted_tools: [],
    withheld_tools: [],
    recommended_model: null,
    ignored_declarations: [],
    mcp_names: [],
    subagent_names: [],
    is_subagent: false,
    is_entry_agent: true,
    virtual_id: 'agent:0',
    conflict: false,
    existing_agent_id: null,
    existing_is_built_in: false,
    unresolved_skills: [],
    unresolved_connectors: [],
    unresolved_subagents: [],
    ...overrides,
  };
}

export function previewPayload(overrides: Partial<PluginPreviewPayload> = {}): PluginPreviewPayload {
  return {
    session_id: 'sess-1',
    plugin: {
      name: 'reports-plugin',
      version: '1.0.0',
      description: 'PDF report generation',
      author: { name: 'Alice' },
      homepage: null,
      repository: null,
      license: 'MIT',
      keywords: ['pdf'],
      capabilities: [],
      effective_tier: 'read_only',
      risk_level: 'low',
      capability_diff: null,
    },
    skills: [],
    servers: [],
    agents: [],
    workspace_file_count: 0,
    deployment: { allows_local_skills: true, allow_stdio: true },
    diagnostics: [],
    is_valid: true,
    ...overrides,
  };
}

export function confirmResult(overrides: Partial<PluginConfirmResult> = {}): PluginConfirmResult {
  return {
    imported_skills: 0,
    skipped_skills: 0,
    imported_servers: 0,
    skipped_servers: 0,
    imported_agents: 0,
    skipped_agents: 0,
    required_secret_keys: [],
    created_agent_ids: [],
    agents: [],
    failures: [],
    ...overrides,
  };
}
