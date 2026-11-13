/**
 * [POS]
 * Agent-config domain facade. Explicit re-export list is the compiler-enforced
 * public surface: adding an export inside the package without listing it
 * here leaves it package-private (typecheck breaks consumer imports instead
 * of silently leaking symbols).
 */
export { buildAgentConfig } from './agentConfigMapper';
export { buildMissingDependenciesParts, validateAgentDependencies } from './agentConfigValidator';
export {
  areBindingsEqual,
  findBindingIssues,
  normalizeBinding,
  parseAliasList,
  sanitizeCommandToken,
  toBindingsPayload,
} from './commandBindings';
export { areSkillConfigsEqual } from './skillConfigs';
export type { BindingIssue } from './commandBindings';
export type { ValidationResult } from './agentConfigValidator';
