/**
 * [INPUT]
 * - @/components/features/chat-window/final-card/finalCardTypes
 *
 * [OUTPUT]
 * - formatDurationText, formatSizeBytes, assembleFinalCardContract, validateFinalCardContract
 *
 * [POS]
 * Pure computation engine for Item 192 (P0).
 * Implements final presentation card assembly, formatting, and runtime contract validation.
 */

import type {
  FinalCardStatus,
  FinalCardActionOption,
  FinalCardArtifact,
  FinalCardPresentationContract,
} from './finalCardTypes';

export function formatDurationText(ms: number): string {
  if (ms <= 0) {
    return '0s';
  }
  if (ms < 1000) {
    return `${ms}ms`;
  }
  if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}

export function formatSizeBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) {
    return '0 B';
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function assembleFinalCardContract(params: {
  turnId: string;
  title: string;
  summary: string;
  status?: FinalCardStatus;
  keyDecisions?: readonly string[];
  artifacts?: readonly FinalCardArtifact[];
  actionOptions?: readonly FinalCardActionOption[];
  executionDurationMs?: number;
  tokensUsed?: {
    prompt: number;
    completion: number;
    total: number;
  };
  transcriptUrl?: string;
  rawLogsPreview?: readonly string[];
}): FinalCardPresentationContract {
  const status = params.status ?? 'completed';
  const rawLogs = params.rawLogsPreview ?? [];
  const cardId = `final_card_${params.turnId}_${Date.now()}`;

  return {
    id: cardId,
    turnId: params.turnId,
    status,
    title: params.title,
    summary: params.summary,
    keyDecisions: params.keyDecisions ?? [],
    artifacts: params.artifacts ?? [],
    actionOptions: params.actionOptions ?? [],
    executionDurationMs: params.executionDurationMs ?? 0,
    tokensUsed: params.tokensUsed,
    transcriptUrl: params.transcriptUrl ?? `/api/transcripts/${params.turnId}`,
    rawLogLinesCount: rawLogs.length,
    rawLogsPreview: rawLogs,
    timestamp: Date.now(),
  };
}

export function validateFinalCardContract(contract: unknown): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  if (!contract || typeof contract !== 'object') {
    return { valid: false, errors: ['Contract must be a non-null object'] };
  }

  const c = contract as Record<string, unknown>;

  if (typeof c.id !== 'string' || !c.id.trim()) {
    errors.push('id must be a non-empty string');
  }
  if (typeof c.turnId !== 'string' || !c.turnId.trim()) {
    errors.push('turnId must be a non-empty string');
  }
  if (typeof c.title !== 'string' || !c.title.trim()) {
    errors.push('title must be a non-empty string');
  }
  if (typeof c.summary !== 'string') {
    errors.push('summary must be a string');
  }
  if (!Array.isArray(c.keyDecisions)) {
    errors.push('keyDecisions must be an array');
  }
  if (!Array.isArray(c.artifacts)) {
    errors.push('artifacts must be an array');
  }
  if (!Array.isArray(c.actionOptions)) {
    errors.push('actionOptions must be an array');
  }
  if (typeof c.transcriptUrl !== 'string' || !c.transcriptUrl.trim()) {
    errors.push('transcriptUrl must be a non-empty string');
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
