/**
 * [INPUT]
 * ./projectHierarchyTypes
 * ./workspaceProjectManager
 *
 * [OUTPUT]
 * Re-exports for WorkspaceProjectManager and project hierarchy models
 *
 * [POS]
 * myrm-agent-frontend/src/store/projectWorkspace/index.ts
 */

export {
  type ProjectContainer,
  type TopicSessionBranch,
  type BranchInheritancePolicy,
  type IntentNamingResult,
} from './projectHierarchyTypes';

export {
  WorkspaceProjectManager,
  type CreateProjectParams,
} from './workspaceProjectManager';
