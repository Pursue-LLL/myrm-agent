/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CompactedMilestoneCard } from '../CompactedMilestoneCard';
import type { CompactionEntry } from '../compactionTypes';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => {
    if (values && 'count' in values && 'tokens' in values) {
      return `${key}:${String(values.count)}:${String(values.tokens)}`;
    }
    if (values && 'count' in values) {
      return `${key}:${String(values.count)}`;
    }
    return key;
  },
}));

const mockEntry: CompactionEntry = {
  id: 'compaction-card-1',
  compactedAt: '2026-10-12T12:00:00Z',
  compactedMessagesCount: 36,
  savedTokens: 68400,
  goal: 'Implement dual-mode layout and auxiliary workbench',
  progress: 'Refactored file tree, terminals and diff editors',
  keyDecisions: [
    'Decoupled Zustand store for layout states',
    'Applied Tailwind CSS responsive split views',
  ],
  nextSteps: [
    'Execute comprehensive Vitest suites',
    'Verify oxlint 0-warning baseline',
  ],
  criticalContext: 'Preserve existing message list scroll positions',
  filesTouched: ['src/services/workbench.ts', 'src/store/useWorkbenchStore.ts'],
  originalMessages: [
    {
      id: 'orig-1',
      role: 'user',
      content: 'Can we enhance the workbench drawer?',
    },
    {
      id: 'orig-2',
      role: 'assistant',
      content: 'Yes, designing tabs for terminal, diff, and files.',
    },
  ],
};

describe('CompactedMilestoneCard component', () => {
  it('renders capsule header with compacted count and token savings by default', () => {
    render(<CompactedMilestoneCard entry={mockEntry} />);

    expect(screen.getByText('capsuleTitle')).toBeDefined();
    expect(screen.getByText('36 msgs')).toBeDefined();
    expect(screen.getByText('+68,400 tokens')).toBeDefined();

    // 5-section body should be collapsed initially
    expect(screen.queryByText('goalTitle')).toBeNull();
  });

  it('expands 5-section structured summary on header click', () => {
    render(<CompactedMilestoneCard entry={mockEntry} />);

    const header = screen.getByText('capsuleTitle').closest('div');
    expect(header).toBeDefined();
    if (header) {
      fireEvent.click(header);
    }

    // Now 5 sections and touched files should be visible
    expect(screen.getByText('goalTitle')).toBeDefined();
    expect(screen.getByText('Implement dual-mode layout and auxiliary workbench')).toBeDefined();

    expect(screen.getByText('progressTitle')).toBeDefined();
    expect(screen.getByText('Refactored file tree, terminals and diff editors')).toBeDefined();

    expect(screen.getByText('keyDecisionsTitle')).toBeDefined();
    expect(screen.getByText('Decoupled Zustand store for layout states')).toBeDefined();

    expect(screen.getByText('nextStepsTitle')).toBeDefined();
    expect(screen.getByText('Execute comprehensive Vitest suites')).toBeDefined();

    expect(screen.getByText('criticalContextTitle')).toBeDefined();
    expect(screen.getByText('Preserve existing message list scroll positions')).toBeDefined();

    // Touched files
    expect(screen.getByText('src/services/workbench.ts')).toBeDefined();
    expect(screen.getByText('src/store/useWorkbenchStore.ts')).toBeDefined();
  });

  it('toggles time machine drawer when clicking time machine button', () => {
    render(<CompactedMilestoneCard entry={mockEntry} defaultExpanded />);

    expect(screen.getByText('goalTitle')).toBeDefined();
    expect(screen.queryByLabelText('Read-Only Transcript Time Machine')).toBeNull();

    // Click time machine entrance button
    const timeMachineBtn = screen.getByRole('button', { name: /timeMachine\.openButton/i });
    fireEvent.click(timeMachineBtn);

    // Time machine is revealed
    expect(screen.getByLabelText('Read-Only Transcript Time Machine')).toBeDefined();
    expect(screen.getByText('Can we enhance the workbench drawer?')).toBeDefined();

    // Close time machine
    const closeTimeMachineBtn = screen.getByRole('button', { name: /timeMachine\.closeButton/i });
    fireEvent.click(closeTimeMachineBtn);
    expect(screen.queryByLabelText('Read-Only Transcript Time Machine')).toBeNull();
  });
});
