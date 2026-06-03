'use client';

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Plan } from '@/store/chat/goals/usePlanStore';

const basePlan: Plan = {
  goal: 'Add user auth',
  reasoning: 'Need authentication for security',
  steps: [
    {
      step_id: 'step_1',
      description: 'Explore current code',
      expected_output: 'Understanding of existing patterns',
      status: 'pending',
      dependencies: [],
    },
  ],
};

let mockPlanState = {
  plan: basePlan as Plan | null,
  isApproved: false,
  isLoading: false,
  fetchPlan: vi.fn(),
  approvePlan: vi.fn(),
  updateStepStatus: vi.fn(),
  setPlan: vi.fn(),
  setApproved: vi.fn(),
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

vi.mock('@/components/primitives/button', () => ({
  Button: ({
    children,
    ...props
  }: {
    children: React.ReactNode;
    className?: string;
    onClick?: () => void;
    variant?: string;
    size?: string;
  }) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/primitives/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div data-testid="scroll-area">{children}</div>,
}));

vi.mock('@/components/features/kanban/KanbanGraphView', () => ({
  default: () => <div data-testid="kanban-graph" />,
}));

describe('GoalControlPlane', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPlanState = {
      plan: { ...basePlan },
      isApproved: false,
      isLoading: false,
      fetchPlan: vi.fn(),
      approvePlan: vi.fn(),
      updateStepStatus: vi.fn(),
      setPlan: vi.fn(),
      setApproved: vi.fn(),
    };
    mockGoalState = {
      activeGoal: null,
      queuedGoals: [],
      fetchQueue: vi.fn(),
      cancelQueuedGoal: vi.fn(),
      reorderQueue: vi.fn(),
    };
  });

  it('renders pending_issues when not approved and data exists', async () => {
    mockPlanState.plan = {
      ...basePlan,
      pending_issues: ['Use JWT or Session?', 'Need OAuth support?'],
    };

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.getByText('pendingIssues')).toBeDefined();
    expect(screen.getByText('Use JWT or Session?')).toBeDefined();
    expect(screen.getByText('Need OAuth support?')).toBeDefined();
  });

  it('does NOT render pending_issues when approved', async () => {
    mockPlanState.plan = {
      ...basePlan,
      pending_issues: ['Use JWT or Session?'],
    };
    mockPlanState.isApproved = true;

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.queryByText('pendingIssues')).toBeNull();
    expect(screen.queryByText('Use JWT or Session?')).toBeNull();
  });

  it('does NOT render pending_issues section when array is empty', async () => {
    mockPlanState.plan = {
      ...basePlan,
      pending_issues: [],
    };

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.queryByText('pendingIssues')).toBeNull();
  });

  it('does NOT render pending_issues section when field is undefined', async () => {
    mockPlanState.plan = { ...basePlan };

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.queryByText('pendingIssues')).toBeNull();
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

    expect(screen.getByText('Loading plan...')).toBeDefined();
  });

  it('renders approve button when not approved', async () => {
    mockPlanState.isApproved = false;

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.getByText('approveAndExecute')).toBeDefined();
  });

  it('does NOT render approve button when approved', async () => {
    mockPlanState.isApproved = true;

    const { GoalControlPlane } = await import('../goals/GoalControlPlane');
    render(<GoalControlPlane />);

    expect(screen.queryByText('approveAndExecute')).toBeNull();
  });
});
