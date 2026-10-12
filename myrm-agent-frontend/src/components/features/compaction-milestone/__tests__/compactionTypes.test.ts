import { describe, expect, it } from 'vitest';
import type {
  CompactionEntry,
  BranchSummaryEntry,
  CompactedMessageSnapshot,
} from '../compactionTypes';

describe('compactionTypes contract tests', () => {
  it('validates CompactionEntry structured model structure', () => {
    const entry: CompactionEntry = {
      id: 'compaction-001',
      compactedAt: '2026-10-12T12:00:00Z',
      compactedMessagesCount: 36,
      savedTokens: 68400,
      goal: 'Refactor workbench architecture and improve UX',
      progress: 'Completed terminal, diff, and file explorer tabs',
      keyDecisions: ['Adopt Zustand for layout state', 'Use PTY bridge over WebSocket'],
      nextSteps: ['Run integration tests', 'Conduct performance profiling'],
      criticalContext: 'Avoid breaking legacy chat routes during migration',
      filesTouched: ['src/services/workbench.ts', 'src/store/useWorkbenchStore.ts'],
      originalMessages: [
        {
          id: 'msg-1',
          role: 'user',
          content: 'Please refactor the workbench component',
        },
        {
          id: 'msg-2',
          role: 'assistant',
          content: 'I have started building the new tab structure',
        },
      ],
    };

    expect(entry.compactedMessagesCount).toBe(36);
    expect(entry.savedTokens).toBe(68400);
    expect(entry.keyDecisions).toHaveLength(2);
    expect(entry.filesTouched).toHaveLength(2);
    expect(entry.originalMessages).toHaveLength(2);
  });

  it('validates BranchSummaryEntry cross-branch model structure', () => {
    const branchEntry: BranchSummaryEntry = {
      id: 'branch-summary-001',
      sourceBranchId: 'branch-feat-a',
      sourceBranchName: 'Feature-A-Exploration',
      forkedAtMessageId: 'msg-fork-10',
      summary: 'Explored monaco-editor integration vs lightweight textarea fallback',
      keyTakeaways: [
        'Monaco is heavy on bundle size; use custom diff renderer instead',
        'Zustand store allows multi-window synchronization',
      ],
      createdAt: '2026-10-12T12:30:00Z',
    };

    expect(branchEntry.sourceBranchId).toBe('branch-feat-a');
    expect(branchEntry.keyTakeaways).toHaveLength(2);
  });
});
