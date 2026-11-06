import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MemoryBriefData } from '@/store/chat/types';
import MemoryInsightPanel from '../MemoryInsightPanel';

const device = vi.hoisted(() => ({ canHover: true }));

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useMediaQuery: (query: string) => query === '(hover: none)' && !device.canHover,
}));

// Interpolating translator: the card text then exposes the counts it renders.
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key} ${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const READY_BRIEF: MemoryBriefData = {
  snapshot_id: 'snap-1',
  generated_at_ms: 0,
  namespaces: ['global', 'agent:writer'],
  is_cold_start: false,
  stable: { working_state: false, profile_count: 3, instruction_count: 1, rule_count: 2 },
};

const COLD_BRIEF: MemoryBriefData = {
  ...READY_BRIEF,
  is_cold_start: true,
  stable: { working_state: false, profile_count: 0, instruction_count: 0, rule_count: 0 },
};

let originalResizeObserver: typeof globalThis.ResizeObserver | undefined;

describe('MemoryInsightPanel brief card', () => {
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

  beforeEach(() => {
    device.canHover = true;
  });

  it('summarises the stable context on hover, with no learned-context row', async () => {
    const user = userEvent.setup();
    render(<MemoryInsightPanel memoryBrief={READY_BRIEF} />);

    expect(screen.queryByText('briefTitle')).not.toBeInTheDocument();

    await user.hover(screen.getByRole('button', { name: /briefPill/ }));

    expect(await screen.findByText('briefTitle')).toBeInTheDocument();
    expect(screen.getByText('briefStableSummary {"instructions":1,"rules":2,"profiles":3}')).toBeInTheDocument();
    expect(screen.queryByText(/briefLearnedSummary/)).not.toBeInTheDocument();
  });

  it('explains a cold start instead of listing counts', async () => {
    const user = userEvent.setup();
    render(<MemoryInsightPanel memoryBrief={COLD_BRIEF} />);

    await user.hover(screen.getByRole('button', { name: /briefPill/ }));

    expect(await screen.findByText('briefColdStartDescription')).toBeInTheDocument();
    expect(screen.queryByText(/briefStableSummary/)).not.toBeInTheDocument();
  });

  it('opens on tap when the primary input cannot hover', () => {
    device.canHover = false;
    render(<MemoryInsightPanel memoryBrief={READY_BRIEF} />);

    fireEvent.click(screen.getByRole('button', { name: /briefPill/ }));

    expect(screen.getByText('briefTitle')).toBeInTheDocument();
    expect(screen.getByText('briefStableSummary {"instructions":1,"rules":2,"profiles":3}')).toBeInTheDocument();
  });

  it('ignores a bare click when the primary input can hover', () => {
    render(<MemoryInsightPanel memoryBrief={READY_BRIEF} />);

    fireEvent.click(screen.getByRole('button', { name: /briefPill/ }));

    expect(screen.queryByText('briefTitle')).not.toBeInTheDocument();
  });
});
