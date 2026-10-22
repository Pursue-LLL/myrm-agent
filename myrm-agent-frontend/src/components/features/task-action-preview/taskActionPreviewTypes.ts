/**
 * [INPUT] None (Foundation types for task extraction and typed action preview)
 * [OUTPUT] CleanedActionItem, TypedActionPayload, ImmutableOperationReceipt contracts
 * [POS] task-action-preview/taskActionPreviewTypes.ts
 */

export type ActionCategory = 'task' | 'fix' | 'refactor' | 'investigate' | 'verify';

export type ActionUrgency = 'low' | 'medium' | 'high';

export interface CleanedActionItem {
  rawText: string;
  actionableTitle: string;
  suggestedDescription: string;
  category: ActionCategory;
  urgency: ActionUrgency;
  extractedBulletPoints: string[];
}

export type TypedActionCategory =
  | 'goal_lifecycle'
  | 'file_mutation'
  | 'deployment'
  | 'permission_grant'
  | 'batch_cleanup';

export type TypedActionRiskLevel = 'low' | 'moderate' | 'high' | 'critical';

export interface QuotaDeltaItem {
  metric: string;
  before: number | string;
  after: number | string;
}

export interface TypedActionPayload {
  actionId: string;
  category: TypedActionCategory;
  title: string;
  description: string;
  riskLevel: TypedActionRiskLevel;
  targetResourceId: string;
  targetResourceName: string;
  affectedFiles?: string[];
  quotaDelta?: QuotaDeltaItem[];
  sideEffects: string[];
  requiredRole?: string;
  requiresExplicitConfirmation?: boolean;
}

export interface ImmutableOperationReceipt {
  receiptId: string;
  actionId: string;
  actionType: TypedActionCategory;
  operator: string;
  timestamp: number;
  targetSha: string;
  status: 'success' | 'failed' | 'rejected';
  statusCode: number;
  summary: string;
  auditPayloadHash: string;
}
