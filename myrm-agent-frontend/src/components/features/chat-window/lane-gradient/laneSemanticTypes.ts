/**
 * [INPUT]
 * - None (Pure domain type definitions for Lane Semantic Gradient & Auto-Graduation)
 *
 * [OUTPUT]
 * - LaneType, LaneEnvironmentMode, LaneCapability, PersistenceScope, LaneGradientSpec,
 *   GraduationIntentMatch, LaneGraduationEvent, LaneSemanticStoreState
 *
 * [POS]
 * Unified contract for Item 188: ChatLaneVsWorkspaceLaneSemanticGradientAndAutoGraduationSuite.
 * Establishes an authoritative two-lane paradigm ('chat' vs 'workspace') across 3 runtime modes,
 * eradicating ambiguous modal states and governing in-session auto-graduation triggers.
 */

export type LaneType = 'chat' | 'workspace';

export type LaneEnvironmentMode = 'fast_chat' | 'local_workspace' | 'cloud_sandbox';

export type LaneCapability =
  | 'read_only'
  | 'file_write'
  | 'shell_exec'
  | 'web_search'
  | 'code_sandbox'
  | 'git_ops';

export type PersistenceScope = 'ephemeral_memory' | 'local_disk' | 'cloud_container';

export type GraduationTriggerKind =
  | 'file_write'
  | 'shell_command'
  | 'project_scaffold'
  | 'dependency_install'
  | 'git_operation';

export interface LaneGradientSpec {
  readonly laneType: LaneType;
  readonly envMode: LaneEnvironmentMode;
  readonly displayName: string;
  readonly summary: string;
  readonly capabilities: readonly LaneCapability[];
  readonly persistenceScope: PersistenceScope;
  readonly canWriteFiles: boolean;
  readonly canExecCommands: boolean;
  readonly badgeColor: 'sky' | 'emerald' | 'amber' | 'indigo';
}

export interface GraduationIntentMatch {
  readonly triggerKind: GraduationTriggerKind;
  readonly matchedKeyword: string;
  readonly confidence: number;
  readonly reason: string;
  readonly suggestedTargetMode: 'local_workspace' | 'cloud_sandbox';
  readonly detectedSnippet: string;
}

export interface LaneGraduationEvent {
  readonly id: string;
  readonly timestamp: number;
  readonly fromLane: LaneType;
  readonly fromEnvMode: LaneEnvironmentMode;
  readonly toLane: LaneType;
  readonly toEnvMode: LaneEnvironmentMode;
  readonly reason: string;
  readonly workspaceDir: string | null;
}

export interface LaneSemanticStoreState {
  readonly manualLaneOverride: LaneType | null;
  readonly pendingGraduation: GraduationIntentMatch | null;
  readonly isGraduationDialogOpen: boolean;
  readonly graduationHistory: readonly LaneGraduationEvent[];
}
