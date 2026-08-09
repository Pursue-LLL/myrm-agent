import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MemoryLifecycleTimeline } from '@/components/features/message-box/MemoryLifecycleTimeline';
import type { MemoryLifecyclePhaseId, MemoryLifecyclePhaseState } from '@/components/features/message-box/memoryLifecyclePhases';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

function phasesWithExtractError(): Record<MemoryLifecyclePhaseId, MemoryLifecyclePhaseState> {
  return {
    write: { id: 'write', status: 'success' },
    extract: { id: 'extract', status: 'error', detail: 'failed' },
    recall: { id: 'recall', status: 'idle' },
  };
}

describe('MemoryLifecycleTimeline', () => {
  it('shows retry button when extract failed and handler provided', async () => {
    const onRetryExtract = vi.fn(async () => undefined);

    render(
      <MemoryLifecycleTimeline
        phases={phasesWithExtractError()}
        showRecall={false}
        onRetryExtract={onRetryExtract}
      />,
    );

    const retryButton = screen.getByRole('button', { name: 'lifecycleRetryExtract' });
    await userEvent.click(retryButton);

    expect(onRetryExtract).toHaveBeenCalledOnce();
  });

  it('hides retry button when extract is not in error state', () => {
    render(
      <MemoryLifecycleTimeline
        phases={{
          write: { id: 'write', status: 'success' },
          extract: { id: 'extract', status: 'success' },
          recall: { id: 'recall', status: 'idle' },
        }}
        showRecall={false}
        onRetryExtract={vi.fn(async () => undefined)}
      />,
    );

    expect(screen.queryByRole('button', { name: 'lifecycleRetryExtract' })).not.toBeInTheDocument();
  });

  it('shows stored count on extract success', () => {
    render(
      <MemoryLifecycleTimeline
        phases={{
          write: { id: 'write', status: 'success' },
          extract: { id: 'extract', status: 'success', storedCount: 2, durationMs: 500 },
          recall: { id: 'recall', status: 'idle' },
        }}
        showRecall={false}
      />,
    );

    expect(screen.getByText(/lifecycleStoredCount/)).toBeInTheDocument();
    expect(screen.getByText(/lifecycleDurationMs/)).toBeInTheDocument();
  });

  it('shows no-new-cards copy when extract success with zero stored', () => {
    render(
      <MemoryLifecycleTimeline
        phases={{
          write: { id: 'write', status: 'success' },
          extract: { id: 'extract', status: 'success', storedCount: 0, verbatimCount: 0 },
          recall: { id: 'recall', status: 'idle' },
        }}
        showRecall={false}
      />,
    );

    expect(screen.getByText(/lifecycleStoredCountNone/)).toBeInTheDocument();
  });

  it('shows verbatim stored copy when compressed cards are zero', () => {
    render(
      <MemoryLifecycleTimeline
        phases={{
          write: { id: 'write', status: 'success' },
          extract: { id: 'extract', status: 'success', storedCount: 0, verbatimCount: 2 },
          recall: { id: 'recall', status: 'idle' },
        }}
        showRecall={false}
      />,
    );

    expect(screen.getByText(/lifecycleVerbatimStored/)).toBeInTheDocument();
    expect(screen.queryByText(/lifecycleStoredCountNone/)).not.toBeInTheDocument();
  });
});
