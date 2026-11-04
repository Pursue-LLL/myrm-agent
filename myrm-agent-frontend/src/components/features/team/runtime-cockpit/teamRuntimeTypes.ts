export type DAGNodeStatus = 'pending' | 'running' | 'completed' | 'failed' | 'stale_prerequisite';

export type DAGNodeType = 'leader' | 'researcher' | 'architect' | 'evaluator' | 'finalizer';

export interface DeliverablePacket {
  deliverableId: string;
  version: number;
  summary: string;
  decidedFacts: string[];
  pendingRisksAndExceptions: string[];
  updatedAt: string;
}

export interface DAGNode {
  id: string;
  label: string;
  type: DAGNodeType;
  assigneeAgentName: string;
  status: DAGNodeStatus;
  dependencies: string[];
  deliverable?: DeliverablePacket;
  staleReason?: string;
}

export interface ConflictOption {
  id: string;
  title: string;
  impactAnalysis: string;
  actionDirective: string;
}

export interface TeamConflictItem {
  id: string;
  title: string;
  sourceNodeIds: string[];
  conflictDescription: string;
  options: ConflictOption[];
  status: 'pending_arbitration' | 'resolved';
  selectedOptionId?: string;
  arbitratedAt?: string;
}

export interface CoordinationTelemetry {
  preventedAlignmentsCount: number;
  savedManualMinutes: number;
  blockedBlindRerunsCount: number;
  coordinationHealthScore: number;
}

export interface TeamRuntimeState {
  teamName: string;
  nodes: DAGNode[];
  conflicts: TeamConflictItem[];
  selectedNodeId: string | null;
  activeConflictId: string | null;
  isDrawerOpen: boolean;
  telemetry: CoordinationTelemetry;

  selectNode: (nodeId: string | null) => void;
  openConflictModal: (conflictId: string) => void;
  closeConflictModal: () => void;
  closeDrawer: () => void;
  updateNodeDeliverable: (nodeId: string, updatedSummary: string, newFacts: string[]) => void;
  arbitrateConflict: (conflictId: string, optionId: string) => void;
  resetTeamRuntimeState: () => void;
}
