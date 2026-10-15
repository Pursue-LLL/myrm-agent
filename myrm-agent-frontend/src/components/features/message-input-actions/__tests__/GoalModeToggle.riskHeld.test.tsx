// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { fetchMock, sonnerToast, riskToast, chatState } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  chatState: {
    actionMode: 'agent',
    isGoalMode: true,
    inputMessage: 'Ship it with key sk-AAAAAABBBBBBCCCCCCDDDD-0',
    goalAcceptanceCriteria: null,
    goalConstraints: null,
    goalProtectedPaths: null,
    setIsGoalMode: vi.fn(),
    setGoalBudgetTokens: vi.fn(),
    setGoalBudgetUsd: vi.fn(),
    setGoalMaxTimeSeconds: vi.fn(),
    setGoalMaxTurns: vi.fn(),
    setGoalProtectedPaths: vi.fn(),
    setGoalLoopOnPause: vi.fn(),
    setGoalConvergenceWindow: vi.fn(),
    setGoalAcceptanceCriteria: vi.fn(),
    setGoalConstraints: vi.fn(),
    setGoalCheckpointMode: vi.fn(),
  } as Record<string, unknown>,
}));

vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('@/store/useChatStore', () => ({
  default: (select: (state: Record<string, unknown>) => unknown) => select(chatState),
}));
vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: (select: (state: { initialized: boolean; enabledFeatures: Set<string> }) => unknown) =>
    select({ initialized: false, enabledFeatures: new Set() }),
}));

import GoalModeToggle from '../GoalModeToggle';

/** Opens the popover and presses "suggest criteria" with the composer text above. */
async function suggestCriteria(): Promise<void> {
  render(<GoalModeToggle />);
  fireEvent.click(screen.getAllByRole('button', { name: 'enableGoalMode' })[0] as HTMLElement);
  fireEvent.click(await screen.findByTestId('goal-draft-suggest'));
}

describe('suggesting goal criteria for an objective the server holds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  it('explains the held objective once instead of claiming the draft could not be generated', async () => {
    fetchMock.mockResolvedValue(jsonResponse(400, riskHeldRefusalBody));

    await suggestCriteria();

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(chatState.setGoalAcceptanceCriteria).not.toHaveBeenCalled();
  });

  it('still reports any other draft failure with its own toast', async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, { detail: 'boom' }));

    await suggestCriteria();

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('draftFailed'));
    expect(riskToast.error).not.toHaveBeenCalled();
  });
});
