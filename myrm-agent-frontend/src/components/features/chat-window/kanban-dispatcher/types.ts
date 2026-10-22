export type KanbanSwimlane =
  | 'backlog'
  | 'researching'
  | 'developing'
  | 'reviewing'
  | 'done';

export interface HandoffEventItem {
  fromLane: KanbanSwimlane;
  toLane: KanbanSwimlane;
  fromAgent: string;
  toAgent: string;
  timestampUtc: string;
  notes?: string;
}

export interface KanbanCardItem {
  cardId: string;
  title: string;
  description: string;
  swimlane: KanbanSwimlane;
  assignedAgentId: string;
  progressPct: number;
  isBlocked: boolean;
  blockReason?: string;
  handoffHistory: HandoffEventItem[];
  tags: string[];
  createdAtUtc: string;
  updatedAtUtc: string;
}

export interface KanbanBoardState {
  chatId: string;
  cards: KanbanCardItem[];
  swimlanes: KanbanSwimlane[];
  totalCards: number;
  blockedCount: number;
  doneCount: number;
}

export const SWIMLANE_CONFIG: Record<
  KanbanSwimlane,
  { label: string; defaultAgent: string; color: string }
> = {
  backlog: {
    label: 'Backlog',
    defaultAgent: 'product_manager',
    color: 'border-slate-600 bg-slate-800/40 text-slate-300',
  },
  researching: {
    label: 'Researching',
    defaultAgent: 'research_specialist',
    color: 'border-cyan-600 bg-cyan-950/30 text-cyan-300',
  },
  developing: {
    label: 'Developing',
    defaultAgent: 'dev_coder',
    color: 'border-indigo-600 bg-indigo-950/30 text-indigo-300',
  },
  reviewing: {
    label: 'Reviewing',
    defaultAgent: 'reviewer_critic',
    color: 'border-amber-600 bg-amber-950/30 text-amber-300',
  },
  done: {
    label: 'Done',
    defaultAgent: 'qa_release_bot',
    color: 'border-emerald-600 bg-emerald-950/30 text-emerald-300',
  },
};

export const SWIMLANE_ORDER: KanbanSwimlane[] = [
  'backlog',
  'researching',
  'developing',
  'reviewing',
  'done',
];

export const INITIAL_DEMO_CARDS: KanbanCardItem[] = [
  {
    cardId: 'card-101',
    title: 'Analyze Vector Index Latency Bottleneck',
    description: 'Perform profiling on HNSW cosine distance calculations under high QPS.',
    swimlane: 'researching',
    assignedAgentId: 'research_specialist',
    progressPct: 45,
    isBlocked: false,
    handoffHistory: [
      {
        fromLane: 'backlog',
        toLane: 'researching',
        fromAgent: 'product_manager',
        toAgent: 'research_specialist',
        timestampUtc: '2026-10-15T08:00:00Z',
        notes: 'Handed off for in-depth performance benchmarks.',
      },
    ],
    tags: ['performance', 'vector-db'],
    createdAtUtc: '2026-10-15T07:45:00Z',
    updatedAtUtc: '2026-10-15T08:00:00Z',
  },
  {
    cardId: 'card-102',
    title: 'Implement Rust SIMD Vector Normalization',
    description: 'Port AVX2 vector normalization kernel to Neon/AVX-512 with bounds verification.',
    swimlane: 'developing',
    assignedAgentId: 'dev_coder',
    progressPct: 70,
    isBlocked: true,
    blockReason: 'Awaiting upstream SIMD intrinsic stabilization branch approval.',
    handoffHistory: [
      {
        fromLane: 'backlog',
        toLane: 'researching',
        fromAgent: 'product_manager',
        toAgent: 'research_specialist',
        timestampUtc: '2026-10-15T08:10:00Z',
        notes: 'Spike approved.',
      },
      {
        fromLane: 'researching',
        toLane: 'developing',
        fromAgent: 'research_specialist',
        toAgent: 'dev_coder',
        timestampUtc: '2026-10-15T08:30:00Z',
        notes: 'Algorithm validated, handed off for implementation.',
      },
    ],
    tags: ['rust', 'simd', 'blocked'],
    createdAtUtc: '2026-10-15T08:05:00Z',
    updatedAtUtc: '2026-10-15T08:45:00Z',
  },
  {
    cardId: 'card-103',
    title: 'Audit Multi-Tenant Memory Leaks',
    description: 'Static and runtime analysis on SharedTokenBudgetGovernor under eviction.',
    swimlane: 'reviewing',
    assignedAgentId: 'reviewer_critic',
    progressPct: 90,
    isBlocked: false,
    handoffHistory: [
      {
        fromLane: 'developing',
        toLane: 'reviewing',
        fromAgent: 'dev_coder',
        toAgent: 'reviewer_critic',
        timestampUtc: '2026-10-15T09:00:00Z',
        notes: 'Patch completed, ready for audit.',
      },
    ],
    tags: ['security', 'audit'],
    createdAtUtc: '2026-10-15T08:20:00Z',
    updatedAtUtc: '2026-10-15T09:00:00Z',
  },
  {
    cardId: 'card-104',
    title: 'PR #418 Verification & Release Notes',
    description: 'Verify end-to-end telemetry and publish release descriptor.',
    swimlane: 'done',
    assignedAgentId: 'qa_release_bot',
    progressPct: 100,
    isBlocked: false,
    handoffHistory: [
      {
        fromLane: 'reviewing',
        toLane: 'done',
        fromAgent: 'reviewer_critic',
        toAgent: 'qa_release_bot',
        timestampUtc: '2026-10-15T09:20:00Z',
        notes: 'All checks passed, marked as done.',
      },
    ],
    tags: ['release', 'qa'],
    createdAtUtc: '2026-10-15T08:15:00Z',
    updatedAtUtc: '2026-10-15T09:20:00Z',
  },
];

export interface VisualKanbanWorkflowDispatcherCardProps {
  chatId?: string;
  initialCards?: KanbanCardItem[];
  onDismiss?: () => void;
  onCardHandoff?: (cardId: string, toLane: KanbanSwimlane, newAgent: string) => void;
  onCardToggleBlock?: (cardId: string, isBlocked: boolean, reason?: string) => void;
  onCardCreated?: (card: KanbanCardItem) => void;
}
