'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { GoalState } from '../goals/GoalStatusCard';

const makeGoal = (overrides: Partial<GoalState> = {}): GoalState => ({
  goalId: 'goal-1',
  objective: 'Test objective',
  status: 'active',
  tokensUsed: 4000,
  timeUsedSeconds: 120,
  costUsd: 0.012,
  budget: {
    maxTokens: 100000,
    maxTimeSeconds: 3600,
    maxUsd: 0.5,
  },
  ...overrides,
});

let mockGoalState: {
  activeGoal: GoalState | null;
  gitBranch: string | null;
  queuedGoals: Array<{ goal_id: string; objective: string }>;
  fetchQueue: ReturnType<typeof vi.fn>;
};

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'test-chat' })),
}));

vi.mock('@/store/chat/goals/useGoalStore', () => ({
  useGoalStore: Object.assign(
    vi.fn((selector?: (state: typeof mockGoalState) => unknown) => {
      if (selector) return selector(mockGoalState);
      return mockGoalState;
    }),
    { getState: () => mockGoalState },
  ),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const map: Record<string, string> = {
      burnRate: 'Speed',
      etaLabel: 'ETA',
      etaCollecting: 'Estimating...',
      statusActive: 'Active',
      timeElapsed: 'Elapsed',
      queueTitle: 'Queue',
    };
    return map[key] ?? key;
  },
}));

vi.mock('@/services/notification', () => ({
  notificationService: {
    isSupported: false,
    permission: 'default' as NotificationPermission,
    requestPermission: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

describe('GoalStatusCard ETA calculations', () => {
  beforeEach(() => {
    mockGoalState = {
      activeGoal: makeGoal(),
      gitBranch: null,
      queuedGoals: [],
      fetchQueue: vi.fn(),
    };
  });

  async function renderCard() {
    const { GoalStatusCard } = await import('../goals/GoalStatusCard');
    return render(<GoalStatusCard />);
  }

  it('shows ETA when sufficient data is available', async () => {
    mockGoalState.activeGoal = makeGoal({
      tokensUsed: 4000,
      timeUsedSeconds: 120,
      budget: { maxTokens: 100000, maxTimeSeconds: 3600 },
    });

    await renderCard();

    expect(screen.getByText(/~48min/)).toBeInTheDocument();
  });

  it('shows "Estimating..." when data is insufficient (<60s)', async () => {
    mockGoalState.activeGoal = makeGoal({
      tokensUsed: 100,
      timeUsedSeconds: 30,
      budget: { maxTokens: 100000 },
    });

    await renderCard();

    expect(screen.getByText('Estimating...')).toBeInTheDocument();
  });

  it('does not show ETA for terminal state (complete)', async () => {
    mockGoalState.activeGoal = makeGoal({
      status: 'complete',
      tokensUsed: 50000,
      timeUsedSeconds: 600,
      budget: { maxTokens: 100000 },
    });

    await renderCard();

    expect(screen.queryByText(/ETA/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Speed/)).not.toBeInTheDocument();
  });

  it('shows burn rate in expanded view for active goal', async () => {
    mockGoalState.activeGoal = makeGoal({
      tokensUsed: 10000,
      timeUsedSeconds: 300,
      budget: { maxTokens: 100000 },
    });

    const { container } = await renderCard();

    // Click the header to expand
    const header = container.querySelector('[class*="cursor-pointer"]');
    if (header) {
      fireEvent.click(header);
    }

    // burnRate = 10000/300*60 = 2000 tok/min => "~2.0K/min"
    expect(screen.getByText(/~2\.0K\/min/)).toBeInTheDocument();
  });

  it('calculates ETA using min of multiple budget dimensions', async () => {
    mockGoalState.activeGoal = makeGoal({
      tokensUsed: 50000,
      timeUsedSeconds: 600,
      costUsd: 0.4,
      budget: {
        maxTokens: 200000,
        maxTimeSeconds: 3600,
        maxUsd: 0.5,
      },
    });

    await renderCard();

    // costUsd rate: 0.4/600 = 0.000667/s => remaining: 0.1/0.000667 = ~150s = ~3min
    // Token rate: 50000/600 = 83.3/s => remaining: 150000/83.3 = ~1800s = ~30min
    // Time remaining: 3600-600 = 3000s = ~50min
    // Min = ~150s => ~3min
    expect(screen.getByText(/~[23]min/)).toBeInTheDocument();
  });

  it('does not show ETA for budget_limited status', async () => {
    mockGoalState.activeGoal = makeGoal({
      status: 'budget_limited',
      tokensUsed: 100000,
      timeUsedSeconds: 1200,
      budget: { maxTokens: 100000 },
    });

    await renderCard();

    expect(screen.queryByText(/~\d+min/)).not.toBeInTheDocument();
  });

  it('formats ETA correctly for hours', async () => {
    mockGoalState.activeGoal = makeGoal({
      tokensUsed: 1000,
      timeUsedSeconds: 60,
      budget: { maxTokens: 1000000 },
    });

    await renderCard();

    // Rate: 1000/60 = 16.67 tok/s => remaining: 999000/16.67 = 59928s => ~16h 39m
    expect(screen.getByText(/~\d+h \d+m/)).toBeInTheDocument();
  });

  it('returns null when no goal is active', async () => {
    mockGoalState.activeGoal = null;

    const { container } = await renderCard();

    expect(container.innerHTML).toBe('');
  });
});
