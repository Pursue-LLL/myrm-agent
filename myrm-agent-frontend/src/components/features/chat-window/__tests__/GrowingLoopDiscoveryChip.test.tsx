/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LearningLoopFiveRingStatusResponse } from '@/services/statistics';
import { GrowingLoopDiscoveryChip } from '../GrowingLoopDiscoveryChip';

const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}|${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));

const statistics = vi.hoisted(() => ({ getLearningLoopStatus: vi.fn() }));

vi.mock('@/services/statistics', () => statistics);

const status: LearningLoopFiveRingStatusResponse = {
  ring1_reflection: { sessions_in_window: 4 },
  ring2_distillation: { cases_total: 206, cases_auto_applied: 11, total_skills: 5 },
  ring3_advancement: { cases_pending_review: 72, cases_blocked: 4 },
  ring4_consolidation: { total_memories: 40 },
  ring5_profiling: { conversations: 9, profile_entries: 3 },
};

describe('GrowingLoopDiscoveryChip', () => {
  beforeEach(() => {
    router.push.mockReset();
    statistics.getLearningLoopStatus.mockReset();
  });

  it('shows the memory and skill counters next to the headline and opens the journey page', async () => {
    statistics.getLearningLoopStatus.mockResolvedValue(status);
    render(<GrowingLoopDiscoveryChip />);

    expect(await screen.findByText('growsWithYou')).toBeTruthy();
    expect(screen.getByText(/stats\|\{"memories":40,"skills":5\}/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button'));
    expect(router.push).toHaveBeenCalledWith('/journey');
  });

  it('keeps the entry point but omits the counters when a source could not be read', async () => {
    statistics.getLearningLoopStatus.mockResolvedValue({ ...status, ring4_consolidation: null });
    render(<GrowingLoopDiscoveryChip />);

    expect(await screen.findByText('growsWithYou')).toBeTruthy();
    expect(screen.queryByText(/stats\|/)).toBeNull();
    expect(screen.getByText('viewLoop')).toBeTruthy();
  });

  it('renders nothing when the status request fails', async () => {
    statistics.getLearningLoopStatus.mockRejectedValue(new Error('offline'));
    const { container } = render(<GrowingLoopDiscoveryChip />);

    await waitFor(() => expect(statistics.getLearningLoopStatus).toHaveBeenCalledWith(30));
    await act(async () => {
      await Promise.resolve();
    });

    expect(container.firstChild).toBeNull();
  });
});
