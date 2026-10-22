export type CommEventStatus = 'running' | 'completed' | 'failed' | 'waiting';

export interface AgentCommEvent {
  id: string;
  stepIndex: number;
  fromAgent: string;
  toAgent: string;
  action: string;
  payloadSummary: string;
  timestamp: string;
  status: CommEventStatus;
  latencyMs?: number;
}

export interface CommGraphState {
  events: AgentCommEvent[];
  selectedEventId: string | null;
  isLive: boolean;
  returnCursorId: string | null;
  isPipelineInitializing: boolean;

  selectEvent: (eventId: string) => void;
  toggleLive: () => void;
  addCommEvent: (event: Omit<AgentCommEvent, 'id' | 'timestamp'>) => string;
  clearEvents: () => void;
  setPipelineInitializing: (initializing: boolean) => void;
  resetState: () => void;
}
