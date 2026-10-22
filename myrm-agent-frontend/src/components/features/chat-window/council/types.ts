export type DeliberationPhase =
  | 'blind_proposal'
  | 'cross_critique'
  | 'rebuttal'
  | 'consensus_synthesis'
  | 'finalized';

export type CritiqueSeverity = 'low' | 'medium' | 'high' | 'blocker';

export interface CouncilProposalItem {
  proposalId: string;
  memberId: string;
  modelName: string;
  title: string;
  reasoningSteps: string[];
  keyArguments: string[];
  confidenceScore: number;
}

export interface CritiquePointItem {
  critiqueId: string;
  sourceMemberId: string;
  targetMemberId: string;
  targetProposalId: string;
  critiquePoints: string[];
  severity: CritiqueSeverity;
  defenseRebuttal?: string | null;
}

export interface ConsensusVerdictItem {
  verdictId: string;
  finalDecision: string;
  confidenceRating: number;
  keyTradeoffs: string[];
  participatingModels: string[];
  dissentingOpinions: string[];
}

export interface CouncilSessionItem {
  sessionId: string;
  deliberationTopic: string;
  phase: DeliberationPhase;
  proposals: Record<string, CouncilProposalItem>;
  critiques: CritiquePointItem[];
  consensus?: ConsensusVerdictItem | null;
  createdAt: number;
  updatedAt: number;
}

export interface CouncilOfAgentsDeliberationCardProps {
  sessionId?: string;
  initialSession?: CouncilSessionItem;
  onDismiss?: () => void;
  onPhaseAdvanced?: (newPhase: DeliberationPhase) => void;
  onConsensusReached?: (verdict: ConsensusVerdictItem) => void;
}

export const INITIAL_COUNCIL_SESSION: CouncilSessionItem = {
  sessionId: 'council-sess-default',
  deliberationTopic: 'Architecture Selection: Stateful Actor Mesh vs Stateless Event-Driven Gateway',
  phase: 'blind_proposal',
  proposals: {
    'prop-claude': {
      proposalId: 'prop-claude',
      memberId: 'agent-claude',
      modelName: 'Claude-3.5-Sonnet',
      title: 'Stateful Durable Actor Mesh with Virtual Actors',
      reasoningSteps: [
        'Local in-memory state caching eliminates database roundtrips.',
        'Single-writer concurrency guarantees zero race conditions.',
        'Deterministic state replay from event journal simplifies disaster recovery.',
      ],
      keyArguments: ['Sub-millisecond state access', 'Zero database lock contention'],
      confidenceScore: 0.94,
    },
    'prop-gpt4o': {
      proposalId: 'prop-gpt4o',
      memberId: 'agent-gpt4o',
      modelName: 'GPT-4o',
      title: 'Stateless Event-Driven Gateway with Redis Cache-Aside',
      reasoningSteps: [
        'Horizontal auto-scaling is seamless with zero node state affinity.',
        'Existing Redis infrastructure requires no paradigm shift for team.',
        'Simpler deployment pipeline and rolling updates without cluster rebalancing.',
      ],
      keyArguments: ['Simpler operational model', 'Cost-effective elastic scaling'],
      confidenceScore: 0.88,
    },
    'prop-deepseek': {
      proposalId: 'prop-deepseek',
      memberId: 'agent-deepseek',
      modelName: 'DeepSeek-R1',
      title: 'Hybrid Tier: Stateless Router with Scoped Actor Workers',
      reasoningSteps: [
        'Separates edge ingress routing from compute-intensive state machines.',
        'Critical transactions run on scoped actors; bulk queries hit read-replicas.',
        'Balances peak throughput with architectural resilience.',
      ],
      keyArguments: ['Targeted isolation of complex workflows', 'Flexible compute allocation'],
      confidenceScore: 0.91,
    },
  },
  critiques: [
    {
      critiqueId: 'crit-01',
      sourceMemberId: 'agent-gpt4o',
      targetMemberId: 'agent-claude',
      targetProposalId: 'prop-claude',
      critiquePoints: ['Cluster split-brain risk during network partitions requires complex Raft arbitration.'],
      severity: 'high',
      defenseRebuttal: 'Built-in quorum fencing and etcd-backed leases eliminate split-brain write hazards.',
    },
    {
      critiqueId: 'crit-02',
      sourceMemberId: 'agent-deepseek',
      targetMemberId: 'agent-gpt4o',
      targetProposalId: 'prop-gpt4o',
      critiquePoints: ['Cache stampede under high concurrent updates will hammer primary PostgreSQL.'],
      severity: 'medium',
      defenseRebuttal: null,
    },
  ],
  consensus: null,
  createdAt: Date.now() - 1000 * 60 * 10,
  updatedAt: Date.now() - 1000 * 60 * 2,
};
