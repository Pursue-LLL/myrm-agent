// @vitest-environment jsdom
/**
 * The goal controls of the card answer a double click and a goal that is still finishing its last step.
 *
 * Real scenario: the user pauses a goal and presses resume right away. The goal's last step is still winding down, so
 * the server refuses and the goal stays paused; the card says to try again in a moment instead of "failed", and the
 * resume button works again. Pressing resume twice in a row asks the server once.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock, chatState, sonnerToast, stableT } = vi.hoisted(() => ({
  stableT: (key: string) => key,
  fetchMock: vi.fn(),
  chatState: { chatId: 'chat-1' },
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('@/components/features/checkpoint/TaskAirbagCapsule', () => ({ TaskAirbagCapsule: () => null }));
vi.mock('@/services/notification', () => ({
  notificationService: { permission: 'default', requestPermission: vi.fn() },
}));
vi.mock('@/store/useChatStore', () => ({
  default: Object.assign((selector: (state: typeof chatState) => unknown) => selector(chatState), {
    getState: () => chatState,
  }),
}));

import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { normalizeGoalState } from '@/store/chat/messageStream/streamHelpers';
import { GoalStatusCard } from '../GoalStatusCard';
import type { GoalStatus } from '../goalStatusTypes';

const jsonResponse = (status: number, body: unknown = {}) => new Response(JSON.stringify(body), { status });

const isStatusPost = ([url, init]: unknown[]) =>
  String(url).endsWith('/goals/chat-1/status') && (init as RequestInit | undefined)?.method === 'POST';

/** Answers the card's startup requests with an empty success, and the status POSTs with `reply`. */
function answerStatusPostsWith(reply: () => Promise<Response>): void {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    isStatusPost([url, init]) ? reply() : jsonResponse(200),
  );
}

function openCard(status: GoalStatus): void {
  useGoalStore.setState({
    chatId: chatState.chatId,
    activeGoal: normalizeGoalState({
      goal_id: 'g1',
      objective: 'Ship it',
      status,
      tokens_used: 0,
      time_used_seconds: 0,
    }),
  });
  render(<GoalStatusCard />);
}

const resumeButton = () => screen.getByRole('button', { name: 'usageLimitResume' });
const statusPosts = () => fetchMock.mock.calls.filter(isStatusPost);
const postedActions = () => statusPosts().map(([, init]) => JSON.parse(String((init as RequestInit).body)));

describe('GoalStatusCard goal controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    chatState.chatId = 'chat-1';
  });

  it('asks the server once when resume is pressed twice, and holds the controls until it answers', async () => {
    let answer: (response: Response) => void = () => undefined;
    answerStatusPostsWith(() => new Promise<Response>((resolve) => (answer = resolve)));
    openCard('paused');

    fireEvent.click(resumeButton());
    await waitFor(() => expect(resumeButton()).toBeDisabled());
    expect(screen.getByRole('button', { name: 'cancel' })).toBeDisabled();
    fireEvent.click(resumeButton());
    expect(statusPosts()).toHaveLength(1);

    answer(jsonResponse(200));
    await waitFor(() => expect(useGoalStore.getState().activeGoal?.status).toBe('active'));
    expect(sonnerToast.success).toHaveBeenCalledTimes(1);
    expect(sonnerToast.success).toHaveBeenCalledWith('goalActionSuccess_resume');
    expect(screen.getByRole('button', { name: 'cancel' })).toBeEnabled();
  });

  it('says the goal is still finishing its last step, and keeps it paused, when the server refuses the resume', async () => {
    answerStatusPostsWith(async () => jsonResponse(409, { detail: 'The goal previous turn is still stopping' }));
    openCard('paused');

    fireEvent.click(resumeButton());

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('goalActionBusy'));
    expect(sonnerToast.error).toHaveBeenCalledTimes(1);
    expect(sonnerToast.success).not.toHaveBeenCalled();
    expect(useGoalStore.getState().activeGoal?.status).toBe('paused');
    await waitFor(() => expect(resumeButton()).toBeEnabled());
  });

  it('puts a waiting goal back to work the same way', async () => {
    answerStatusPostsWith(async () => jsonResponse(200));
    openCard('wait');

    fireEvent.click(resumeButton());

    await waitFor(() => expect(sonnerToast.success).toHaveBeenCalledWith('goalActionSuccess_unwait'));
    expect(postedActions()).toEqual([{ action: 'unwait' }]);
    expect(useGoalStore.getState().activeGoal?.status).toBe('active');
  });

  it('names the control that failed and lets it be pressed again', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    answerStatusPostsWith(async () => jsonResponse(500));
    openCard('paused');

    fireEvent.click(resumeButton());

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('goalActionFailed_resume'));
    expect(useGoalStore.getState().activeGoal?.status).toBe('paused');
    await waitFor(() => expect(resumeButton()).toBeEnabled());
  });
});
