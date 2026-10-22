/**
 * [INPUT] Subagent in-flight state, steer payloads, task summaries
 * [OUTPUT] InFlightSteer type definitions and contracts
 * [POS] Features -> Chat Window -> In-Flight Steer -> Types
 */

export type SubagentRunStatus = 'running' | 'idle' | 'paused' | 'stopped' | 'completed';

export interface PartialDeliverableSnapshot {
  title: string;
  summary: string;
  contentSnippet?: string;
  capturedAt: number;
}

export interface ActiveSubagentSwimlane {
  id: string;
  name: string;
  role: string;
  status: SubagentRunStatus;
  currentStep: string;
  tokensUsed: number;
  elapsedSeconds: number;
  taskId?: string;
  partialDeliverable?: PartialDeliverableSnapshot;
  lastSteeredAt?: number;
  lastInstruction?: string;
}

export interface SteerPresetOption {
  id: string;
  label: string;
  instruction: string;
}

export interface CollapsibleLongTaskSummary {
  id: string;
  chatId: string;
  goalTitle: string;
  totalSteps: number;
  completedSteps: number;
  currentActiveAgentName: string;
  keyFindings: string[];
  isCollapsed: boolean;
  updatedAt: number;
}

export interface InFlightSteerState {
  swimlanes: ActiveSubagentSwimlane[];
  activePopoverSubagentId: string | null;
  taskSummaries: Record<string, CollapsibleLongTaskSummary>;
  isSteering: boolean;
  registerSwimlane: (swimlane: ActiveSubagentSwimlane) => void;
  updateSwimlaneStatus: (
    id: string,
    status: SubagentRunStatus,
    currentStep?: string,
    tokensUsed?: number,
  ) => void;
  removeSwimlane: (id: string) => void;
  openSteerPopover: (subagentId: string) => void;
  closeSteerPopover: () => void;
  sendSteerInstruction: (subagentId: string, instruction: string) => Promise<boolean>;
  stopAndKeepArtifacts: (subagentId: string) => Promise<boolean>;
  setTaskSummary: (summary: CollapsibleLongTaskSummary) => void;
  toggleSummaryCollapse: (summaryId: string) => void;
  clearSwimlanes: () => void;
}
