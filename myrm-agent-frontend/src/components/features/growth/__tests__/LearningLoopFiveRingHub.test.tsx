/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LearningLoopFiveRingStatusResponse } from '@/services/statistics';
import { LearningLoopFiveRingHub } from '../LearningLoopFiveRingHub';

// Echoes the key together with its interpolation values so tests can assert which counter fills which label.
const stableT = (key: string, values?: Record<string, unknown>) => (values ? `${key}|${JSON.stringify(values)}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => router }));

const statistics = vi.hoisted(() => ({ getLearningLoopStatus: vi.fn() }));

vi.mock('@/services/statistics', () => statistics);

vi.mock('@/lib/api', () => ({ showApiError: vi.fn() }));

const status: LearningLoopFiveRingStatusResponse = {
  ring1_reflection: { sessions_in_window: 4 },
  ring2_distillation: { cases_total: 206, cases_auto_applied: 11 },
  ring3_advancement: { cases_pending_review: 72, cases_blocked: 4 },
  ring4_consolidation: { total_memories: 40 },
  ring5_profiling: { conversations: 9, profile_entries: 3 },
};

const ringButton = (ring: string) => screen.findByRole('button', { name: new RegExp(`${ring}\\.name`) });

describe('LearningLoopFiveRingHub', () => {
  beforeEach(() => {
    router.push.mockReset();
    statistics.getLearningLoopStatus.mockReset();
    statistics.getLearningLoopStatus.mockResolvedValue(status);
  });

  it('opens the dashboard tab of a ring when it is activated, each ring being a real button', async () => {
    const onNavigateTab = vi.fn();
    render(<LearningLoopFiveRingHub onNavigateTab={onNavigateTab} />);

    const first = await ringButton('ring1');
    fireEvent.click(first);
    fireEvent.click(screen.getByRole('button', { name: /ring5\.name/ }));

    expect(first.tagName).toBe('BUTTON');
    expect(onNavigateTab.mock.calls).toEqual([['evolution'], ['graph']]);
  });

  it('sends the ring with cases waiting for review to the settings page where they are handled', async () => {
    const onNavigateTab = vi.fn();
    render(<LearningLoopFiveRingHub onNavigateTab={onNavigateTab} />);

    fireEvent.click(await ringButton('ring3'));

    expect(router.push).toHaveBeenCalledWith('/settings/evolutionPending');
    expect(onNavigateTab).not.toHaveBeenCalled();
  });

  it('labels the refresh button from the translations and reloads the status when it is pressed', async () => {
    render(<LearningLoopFiveRingHub />);

    fireEvent.click(await screen.findByRole('button', { name: 'refresh' }));

    await waitFor(() => expect(statistics.getLearningLoopStatus).toHaveBeenCalledTimes(2));
  });

  it('shows on every ring the counters its source reported, with the lookback window on ring 1', async () => {
    render(<LearningLoopFiveRingHub />);

    const expected: Record<string, string[]> = {
      ring1: ['ring1.metricsSessions|{"count":4,"days":30}'],
      ring2: ['ring2.metricsCases|{"count":206}', 'ring2.metricsAutoApplied|{"count":11}'],
      ring3: ['ring3.metricsPending|{"count":72}', 'ring3.metricsBlocked|{"count":4}'],
      ring4: ['ring4.metricsMemories|{"count":40}'],
      ring5: ['ring5.metricsConversations|{"count":9}', 'ring5.metricsProfile|{"count":3}'],
    };
    for (const [ring, metrics] of Object.entries(expected)) {
      const card = await ringButton(ring);
      for (const metric of metrics) {
        expect(within(card).getByText(metric)).toBeTruthy();
      }
    }
    expect(statistics.getLearningLoopStatus).toHaveBeenCalledWith(30);
  });

  it('marks a ring as unavailable instead of showing zeros when its source could not be read', async () => {
    statistics.getLearningLoopStatus.mockResolvedValue({ ...status, ring3_advancement: null });
    render(<LearningLoopFiveRingHub />);

    const unavailable = await ringButton('ring3');
    const healthy = await ringButton('ring2');

    expect(within(unavailable).getByText('unavailable')).toBeTruthy();
    expect(within(unavailable).queryByText(/ring3\.metrics/)).toBeNull();
    expect(within(healthy).queryByText('unavailable')).toBeNull();
  });

  it('presents counters only, without a composite health score or a verdict badge', async () => {
    render(<LearningLoopFiveRingHub />);

    await ringButton('ring1');

    expect(screen.queryByText(/healthScore|totalLearnings|optimal|warning/)).toBeNull();
  });
});
