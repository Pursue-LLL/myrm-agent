export type CollaboratorType = 'human' | 'agent';

export type BlockType = 'heading' | 'paragraph' | 'code' | 'table' | 'bullet_list';

export type DeltaOperation =
  | 'insert_block'
  | 'update_block'
  | 'delete_block'
  | 'reorder_blocks';

export type ArbitrationStrategy =
  | 'human_priority'
  | 'timestamp_lww'
  | 'isolated_staging_proposal';

export interface CollaboratorItem {
  collaboratorId: string;
  collaboratorType: CollaboratorType;
  name: string;
  principalHumanId?: string;
  roleDescription: string;
  joinedAt: number;
}

export interface DocumentBlockItem {
  blockId: string;
  blockType: BlockType;
  content: string;
  version: number;
  lastAuthorId: string;
  lastUpdatedAt: number;
  leaseHolderId?: string;
  leaseExpiresAt?: number;
}

export interface DeltaEntryItem {
  deltaId: string;
  documentId: string;
  blockId: string;
  operation: DeltaOperation;
  authorId: string;
  authorType: CollaboratorType;
  principalHumanId?: string;
  prevContent: string;
  newContent: string;
  intentReason: string;
  timestamp: number;
  applied: boolean;
}

export interface StagingProposalItem {
  proposalId: string;
  blockId: string;
  authorId: string;
  content: string;
  intentReason: string;
  status: string; // 'pending' | 'accepted' | 'rejected'
  createdAt: number;
}

export interface ConflictRecordItem {
  conflictId: string;
  blockId: string;
  competingAuthors: string[];
  detectedAt: number;
  resolved: boolean;
  resolutionStrategy: ArbitrationStrategy;
  resolutionSummary: string;
}

export interface ArbitrationVerdictItem {
  resolved: boolean;
  winningContent: string;
  strategy: ArbitrationStrategy;
  summary: string;
  stagingProposals: StagingProposalItem[];
  timestamp: number;
}

export const DEFAULT_COLLABORATORS: CollaboratorItem[] = [
  {
    collaboratorId: 'user-alice',
    collaboratorType: 'human',
    name: 'Alice (Lead Architect)',
    roleDescription: 'System Architecture & Requirements Owner',
    joinedAt: Date.now() - 7200000,
  },
  {
    collaboratorId: 'agent-alice-bot',
    collaboratorType: 'agent',
    name: 'Alice Copilot',
    principalHumanId: 'user-alice',
    roleDescription: 'Research & Draft Material Specialist',
    joinedAt: Date.now() - 7200000,
  },
  {
    collaboratorId: 'user-bob',
    collaboratorType: 'human',
    name: 'Bob (Security Auditor)',
    roleDescription: 'Zero-Trust Policy & Cryptography Auditor',
    joinedAt: Date.now() - 3600000,
  },
  {
    collaboratorId: 'agent-bob-bot',
    collaboratorType: 'agent',
    name: 'Bob Copilot',
    principalHumanId: 'user-bob',
    roleDescription: 'Static Analysis & Vulnerability Scanner',
    joinedAt: Date.now() - 3600000,
  },
];

export const DEFAULT_DOC_BLOCKS: DocumentBlockItem[] = [
  {
    blockId: 'block-01-title',
    blockType: 'heading',
    content: 'Enterprise Multi-Cloud Distributed Ledger Protocol',
    version: 1,
    lastAuthorId: 'user-alice',
    lastUpdatedAt: Date.now() - 3600000,
  },
  {
    blockId: 'block-02-exec-summary',
    blockType: 'paragraph',
    content: 'This specification defines the tripartite live document co-authoring state machine coordinating human teams and delegated AI agents.',
    version: 2,
    lastAuthorId: 'agent-alice-bot',
    lastUpdatedAt: Date.now() - 1800000,
  },
  {
    blockId: 'block-03-security-sla',
    blockType: 'paragraph',
    content: 'All node transactions must achieve cryptographic consensus with SLA >= 99.99% availability.',
    version: 3,
    lastAuthorId: 'user-bob',
    lastUpdatedAt: Date.now() - 900000,
  },
];

export const DEFAULT_PROPOSALS: StagingProposalItem[] = [
  {
    proposalId: 'prop-sec-opt-01',
    blockId: 'block-03-security-sla',
    authorId: 'agent-bob-bot',
    content: 'All node transactions must achieve cryptographic consensus with SLA >= 99.999% availability (High Availability Multi-Region).',
    intentReason: 'Automated SLA hardening recommendation from security benchmarks',
    status: 'pending',
    createdAt: Date.now() - 300000,
  },
];
