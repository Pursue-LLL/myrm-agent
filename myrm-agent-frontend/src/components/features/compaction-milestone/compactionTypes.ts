/**
 * [INPUT]
 * - None (Fundamental contract definitions)
 *
 * [OUTPUT]
 * - CompactedMessageSnapshot: Minimal read-only model for archived messages
 * - CompactionEntry: 5-section structured summary model with token economics
 * - BranchSummaryEntry: Cross-branch experience transmission model
 *
 * [POS]
 * Type definitions for Compacted Milestone Card & Branch Summary Visualizer (Item 27).
 * Single file < 120 lines. Zero `any` types.
 */

export interface CompactedMessageSnapshot {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp?: string;
  toolName?: string;
}

export interface CompactionEntry {
  id: string;
  compactedAt: string;
  compactedMessagesCount: number;
  savedTokens: number;
  // 5-section structured summary
  goal: string;
  progress: string;
  keyDecisions: string[];
  nextSteps: string[];
  criticalContext: string;
  filesTouched: string[];
  // Archived original messages for Time Machine audit
  originalMessages: CompactedMessageSnapshot[];
}

export interface BranchSummaryEntry {
  id: string;
  sourceBranchId: string;
  sourceBranchName: string;
  forkedAtMessageId?: string;
  summary: string;
  keyTakeaways: string[];
  createdAt: string;
}
