export type DiamondStage = 'fan_out' | 'reduce' | 'synthesize';

export type AuditorPerspective =
  | 'fact_accuracy'
  | 'timeliness'
  | 'citation_authority';

export type RealityAnchorType =
  | 'exit_code_zero'
  | 'hash_match'
  | 'row_count_match';

export interface RealityAnchorItem {
  anchorType: RealityAnchorType;
  targetId: string;
  expectedValue: string;
  actualValue?: string;
  verified: boolean;
}

export interface AdversarialReviewItem {
  perspective: AuditorPerspective;
  auditorId: string;
  passed: boolean;
  score: number;
  critique: string;
  isolatedContextVerified: boolean;
  timestamp: number;
}

export interface AdversarialVerdictItem {
  passed: boolean;
  totalReviews: number;
  passCount: number;
  reviews: AdversarialReviewItem[];
  anchorChecks: RealityAnchorItem[];
  consensusSummary: string;
  timestamp: number;
}

export interface DiamondNodeItem {
  nodeId: string;
  title: string;
  stage: DiamondStage;
  dependsOn: string[];
  payload: Record<string, string>;
  outputArtifact?: string;
  isPruned: boolean;
  status: string; // 'pending' | 'running' | 'completed' | 'failed'
  createdAt: number;
}

export interface CensusStatusItem {
  dispatchedCount: number;
  receivedCount: number;
  missingNodes: string[];
  isHealthy: boolean;
  retriedNodes: string[];
}

export const DEFAULT_DIAMOND_NODES: DiamondNodeItem[] = [
  {
    nodeId: 'fan-worker-1',
    title: 'Explore Qdrant Vector Engine',
    stage: 'fan_out',
    dependsOn: [],
    payload: { query: 'vector benchmarks' },
    outputArtifact: 'Qdrant p99 latency: 12ms [REF-01]',
    isPruned: false,
    status: 'completed',
    createdAt: Date.now() - 3600000,
  },
  {
    nodeId: 'fan-worker-2',
    title: 'Explore Milvus Distributed Cluster',
    stage: 'fan_out',
    dependsOn: [],
    payload: { query: 'cluster scalability' },
    outputArtifact: 'Milvus horizontal scaling: 100M+ vectors [REF-02]',
    isPruned: false,
    status: 'completed',
    createdAt: Date.now() - 3600000,
  },
  {
    nodeId: 'fan-worker-3',
    title: 'Explore Chroma Embedded Store',
    stage: 'fan_out',
    dependsOn: [],
    payload: { query: 'local dev simplicity' },
    outputArtifact: 'Chroma zero setup for local prototyping [REF-03]',
    isPruned: false,
    status: 'completed',
    createdAt: Date.now() - 3600000,
  },
  {
    nodeId: 'reduce-step-01',
    title: 'Deterministic Map-Reduce Deduplicator',
    stage: 'reduce',
    dependsOn: ['fan-worker-1', 'fan-worker-2', 'fan-worker-3'],
    payload: { goal: 'Vector storage selection' },
    outputArtifact: 'Deduplicated comparison matrix compiled with 0 LLM tokens.',
    isPruned: false,
    status: 'completed',
    createdAt: Date.now() - 1800000,
  },
  {
    nodeId: 'synth-step-02',
    title: 'Top-Tier High Quality Synthesis',
    stage: 'synthesize',
    dependsOn: ['reduce-step-01'],
    payload: { goal: 'Vector storage selection' },
    outputArtifact: 'Consolidated Architecture Synthesis: Qdrant recommended for production.',
    isPruned: false,
    status: 'completed',
    createdAt: Date.now() - 900000,
  },
];

export const DEFAULT_REALITY_ANCHORS: RealityAnchorItem[] = [
  {
    anchorType: 'exit_code_zero',
    targetId: 'pytest_suite',
    expectedValue: '0',
    actualValue: '0',
    verified: true,
  },
  {
    anchorType: 'hash_match',
    targetId: 'sha256_bundle',
    expectedValue: 'a1b2c3d4e5f6',
    actualValue: 'a1b2c3d4e5f6',
    verified: true,
  },
];

export const DEFAULT_VERDICT: AdversarialVerdictItem = {
  passed: true,
  totalReviews: 3,
  passCount: 3,
  consensusSummary: 'Blinded consensus approved (3/3) and all reality anchors verified.',
  timestamp: Date.now() - 600000,
  reviews: [
    {
      perspective: 'fact_accuracy',
      auditorId: 'auditor-fact',
      passed: true,
      score: 0.95,
      critique: 'Factual assertions verified against context',
      isolatedContextVerified: true,
      timestamp: Date.now() - 600000,
    },
    {
      perspective: 'timeliness',
      auditorId: 'auditor-time',
      passed: true,
      score: 0.9,
      critique: 'Current best practices aligned',
      isolatedContextVerified: true,
      timestamp: Date.now() - 600000,
    },
    {
      perspective: 'citation_authority',
      auditorId: 'auditor-cite',
      passed: true,
      score: 0.92,
      critique: 'Properly grounded with structural anchors',
      isolatedContextVerified: true,
      timestamp: Date.now() - 600000,
    },
  ],
  anchorChecks: DEFAULT_REALITY_ANCHORS,
};
