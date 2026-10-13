/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LearningLoopFiveRingStatusResponse } from '@/services/statistics';
import { LearningLoopFiveRingHub } from '../LearningLoopFiveRingHub';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const statistics = vi.hoisted(() => ({ getLearningLoopStatus: vi.fn() }));

vi.mock('@/services/statistics', () => statistics);

vi.mock('@/lib/api', () => ({ showApiError: vi.fn() }));

const status: LearningLoopFiveRingStatusResponse = {
  ring1_reflection: {
    total_traces_analyzed: 4,
    anti_patterns_detected: 1,
    recent_reflection_time: null,
    is_active: true,
    status: 'active',
  },
  ring2_distillation: {
    proposals_generated: 3,
    proposals_approved: 2,
    proposals_pending: 1,
    proposals_rejected: 0,
    total_active_skills: 5,
    is_active: true,
    status: 'active',
  },
  ring3_advancement: {
    evaluations_run: 6,
    regressions_blocked: 1,
    avg_score_boost_pct: 12,
    is_active: true,
    status: 'active',
  },
  ring4_consolidation: {
    consolidation_cycles: 2,
    memories_merged: 7,
    noise_pruned: 3,
    memory_health_score: 0.9,
    total_memories: 40,
    is_active: true,
    status: 'active',
  },
  ring5_profiling: {
    conversations_indexed: 9,
    profile_dimensions: 4,
    cross_session_recall_ready: true,
    is_active: true,
    status: 'active',
  },
  overall_loop_health_score: 88,
  overall_status: 'optimal',
  total_learnings_count: 120,
  summary_text: 'Loop is healthy.',
};

describe('LearningLoopFiveRingHub', () => {
  beforeEach(() => {
    statistics.getLearningLoopStatus.mockReset();
    statistics.getLearningLoopStatus.mockResolvedValue(status);
  });

  it('opens the dashboard tab of a ring when it is activated, each ring being a real button', async () => {
    const onNavigateTab = vi.fn();
    render(<LearningLoopFiveRingHub onNavigateTab={onNavigateTab} />);

    const first = await screen.findByRole('button', { name: /ring1\.name/ });
    fireEvent.click(first);
    fireEvent.click(screen.getByRole('button', { name: /ring5\.name/ }));

    expect(first.tagName).toBe('BUTTON');
    expect(onNavigateTab.mock.calls).toEqual([['evolution'], ['graph']]);
  });

  it('labels the refresh button from the translations and reloads the status when it is pressed', async () => {
    render(<LearningLoopFiveRingHub />);

    fireEvent.click(await screen.findByRole('button', { name: 'refresh' }));

    await waitFor(() => expect(statistics.getLearningLoopStatus).toHaveBeenCalledTimes(2));
  });
});
