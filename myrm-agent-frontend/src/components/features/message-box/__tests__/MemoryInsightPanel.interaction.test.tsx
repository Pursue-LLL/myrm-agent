import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import MemoryInsightPanel from '../MemoryInsightPanel';

let originalResizeObserver: typeof globalThis.ResizeObserver | undefined;

describe('MemoryInsightPanel interaction', () => {
  beforeAll(() => {
    originalResizeObserver = globalThis.ResizeObserver;
    class ResizeObserverMock {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  });

  afterAll(() => {
    if (originalResizeObserver) {
      globalThis.ResizeObserver = originalResizeObserver;
      return;
    }
    Reflect.deleteProperty(globalThis, 'ResizeObserver');
  });

  it('shows unavailable reason copy in hover content', async () => {
    const user = userEvent.setup();
    render(
      <MemoryInsightPanel
        memoryBriefStatus={{
          state: 'skipped',
          injection: { state: 'not_applied', reason: 'recall_mode_tools' },
        }}
      />,
    );

    expect(screen.queryByText('briefUnavailableTitle')).not.toBeInTheDocument();

    await user.hover(screen.getByText('briefUnavailablePill'));
    expect(await screen.findByText('briefUnavailableTitle')).toBeInTheDocument();
    expect(screen.getAllByText('briefUnavailableDescriptionToolsMode').length).toBeGreaterThan(0);
  });
});

