/** @vitest-environment jsdom */
'use client';

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Plan } from '@/store/chat/goals/usePlanStore';

const basePlan: Plan = {
  goal: 'Add user auth',
  reasoning: '',
  steps: [
    {
      step_id: 'step_1',
      description: 'Explore current code',
      expected_output: '',
      status: 'pending',
      dependencies: [],
    },
  ],
};

let mockPlanState = {
  plan: basePlan as Plan | null,
  isLoading: false,
  fetchPlan: vi.fn(),
  updateStepStatus: vi.fn(),
  setPlan: vi.fn(),
  clearPlan: vi.fn(),
  clearActivePlan: vi.fn(),
};

let mockGoalState = {
  activeGoal: null as { status: string } | null,
  queuedGoals: [] as Array<{ goal_id: string; objective: string }>,
  fetchQueue: vi.fn(),
  cancelQueuedGoal: vi.fn(),
  reorderQueue: vi.fn(),
};

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: { chatId: string }) => unknown) => selector({ chatId: 'test-chat-id' })),
}));

vi.mock('@/store/chat/goals/usePlanStore', () => ({
  usePlanStore: Object.assign(
    vi.fn((selector?: (state: typeof mockPlanState) => unknown) => {
      if (selector) return selector(mockPlanState);
      return mockPlanState;
    }),
    { getState: () => mockPlanState },
  ),
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
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div data-testid="scroll-area">{children}</div>,
}));

describe('GoalControlPlane', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPlanState = {
      plan: { ...basePlan },
      isLoading: false,
      fetchPlan: vi.fn(),
      updateStepStatus: vi.fn(),
      setPlan: vi.fn(),
      clearPlan: vi.fn(),
      clearActivePlan: vi.fn(),
    };
    mockGoalState = {
      activeGoal: null,
      queuedGoals: [],
      fetchQueue: vi.fn(),
      cancelQueuedGoal: vi.fn(),
      reorderQueue: vi.fn(),
    };
  });

  it('renders todo steps from plan', async () => {
    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.getByText('1. Explore current code')).toBeDefined();
    expect(screen.getByText('goalPlan')).toBeDefined();
  });

  it('renders null when plan is null and not loading', async () => {
    mockPlanState.plan = null;
    mockPlanState.isLoading = false;

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    const { container } = render(<GoalControlPlane />);

    expect(container.innerHTML).toBe('');
  });

  it('renders loading state', async () => {
    mockPlanState.plan = null;
    mockPlanState.isLoading = true;

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.getByText('loadingProgress')).toBeDefined();
  });
});
