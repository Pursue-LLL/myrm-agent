/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { BatchProjectStatus } from '@/services/batch-directory';
import { BATCH_TONE, BatchListStatusBadge, BatchProjectStatusBadge, BatchTaskStatusBadge } from '../BatchStatusBadges';

afterEach(cleanup);

const tokens = (tone: string) => tone.split(' ');

const PROJECT_TONES: [BatchProjectStatus, string, string][] = [
  ['draft', 'statusDraft', BATCH_TONE.muted],
  ['running', 'statusRunning', BATCH_TONE.active],
  ['paused', 'statusPaused', BATCH_TONE.warning],
  ['completed', 'statusCompleted', BATCH_TONE.success],
  ['failed', 'statusFailed', BATCH_TONE.danger],
  ['cancelled', 'statusCancelled', BATCH_TONE.muted],
];

describe('BATCH_TONE', () => {
  it('uses the readable destructive text token for danger and keeps the tint as a translucent fill', () => {
    expect(tokens(BATCH_TONE.danger)).toEqual(['border-destructive/30', 'bg-destructive/10', 'text-destructive-text']);
  });
});

describe('BatchProjectStatusBadge', () => {
  it.each(PROJECT_TONES)('renders the %s label with its tone', (status, label, tone) => {
    render(<BatchProjectStatusBadge status={status} />);
    expect(screen.getByText(label)).toHaveClass(...tokens(tone));
  });

  it('falls back to the draft style for an unknown status', () => {
    render(<BatchProjectStatusBadge status={'archived' as BatchProjectStatus} />);
    expect(screen.getByText('statusDraft')).toHaveClass(...tokens(BATCH_TONE.muted));
  });
});

describe('BatchListStatusBadge', () => {
  it.each(PROJECT_TONES.filter(([status]) => status !== 'running'))(
    'renders the %s label with an icon and its tone',
    (status, label, tone) => {
      render(<BatchListStatusBadge status={status} />);
      const badge = screen.getByTestId('bd-project-row-status');
      expect(badge).toHaveTextContent(label);
      expect(badge).toHaveClass(...tokens(tone));
      expect(badge.querySelector('svg')).not.toBeNull();
    },
  );

  it('keeps the default accent badge while running, with a spinning icon', () => {
    render(<BatchListStatusBadge status="running" />);
    const badge = screen.getByTestId('bd-project-row-status');
    expect(badge).toHaveTextContent('statusRunning');
    expect(badge).not.toHaveClass('bg-muted/50');
    expect(badge.querySelector('svg')).toHaveClass('animate-spin');
  });

  it('falls back to the draft label and icon for an unknown status', () => {
    render(<BatchListStatusBadge status={'archived' as BatchProjectStatus} />);
    expect(screen.getByTestId('bd-project-row-status')).toHaveTextContent('statusDraft');
  });
});

describe('BatchTaskStatusBadge', () => {
  it.each([
    ['completed', 'taskStatusCompleted', BATCH_TONE.success],
    ['failed', 'taskStatusFailed', BATCH_TONE.danger],
    ['running', 'taskStatusRunning', BATCH_TONE.active],
    ['archived', 'taskStatusArchived', BATCH_TONE.muted],
    ['in_review', 'taskStatusInReview', BATCH_TONE.warning],
    ['blocked', 'taskStatusBlocked', BATCH_TONE.muted],
    ['pending', 'taskStatusPending', BATCH_TONE.muted],
    ['something-new', 'taskStatusPending', BATCH_TONE.muted],
  ])('maps %s to %s', (status, label, tone) => {
    render(<BatchTaskStatusBadge status={status} />);
    const badge = screen.getByText(label);
    expect(badge).toHaveClass(...tokens(tone));
    expect(badge.querySelector('svg')).not.toBeNull();
  });

  it('draws the failed icon in the readable destructive text token', () => {
    render(<BatchTaskStatusBadge status="failed" />);
    const icon = screen.getByText('taskStatusFailed').querySelector('svg');
    expect(icon).toHaveClass('text-destructive-text');
    expect(icon).not.toHaveClass('text-destructive');
  });
});
