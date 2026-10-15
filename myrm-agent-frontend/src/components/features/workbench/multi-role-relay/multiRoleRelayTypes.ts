export type AgentRoleType =
  | 'researcher'
  | 'analyst'
  | 'copywriter'
  | 'reviewer'
  | 'engineer';

export type RelayStageStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'interrupted';

export interface StageArtifactSnapshot {
  id: string;
  stageId: string;
  role: AgentRoleType;
  roleName: string;
  artifactName: string;
  contentType: 'json' | 'markdown' | 'code' | 'table';
  rawContent: string;
  summary: string;
  timestamp: number;
  tokenCount: number;
  version: number;
}

export interface RelayStage {
  id: string;
  stepNumber: number;
  role: AgentRoleType;
  roleName: string;
  status: RelayStageStatus;
  actionSummary: string;
  durationMs: number;
  startedAt?: number;
  completedAt?: number;
  snapshot?: StageArtifactSnapshot;
}

export interface ArtifactForkBranch {
  id: string;
  baseSnapshotId: string;
  stageId: string;
  branchName: string;
  modifiedContent: string;
  userNote?: string;
  createdAt: number;
  status: 'draft' | 'applied';
}

export interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  text: string;
  lineNumber: number;
}
