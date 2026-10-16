// @vitest-environment jsdom
/**
 * Real scenario: the user starts a goal in chat A, then clicks chat B in the sidebar. The card at the top of B must not
 * keep showing A's goal (its buttons would act on B), and a reply to A's request that is still on its way must not
 * bring it back.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock, chatState } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  /** The open chat as the store holds it; a test changes `chatId` and re-renders to open another chat. */
  chatState: {
    chatId: 'chat-a',
    agentConfig: { agentId: 'agent-1' },
    incognitoMode: false,
    inputMessage: '',
    files: [],
    pendingExplicitSkillActivation: null,
    sendMessage: vi.fn(),
    setInputMessage: vi.fn(),
    setFiles: vi.fn(),
    setPendingExplicitSkillActivation: vi.fn(),
  },
}));

vi.mock('sonner', () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));
vi.mock('@/lib/utils/toast', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('@/services/notification', () => ({
  notificationService: { permission: 'default', requestPermission: vi.fn() },
}));
vi.mock('@/store/useChatStore', () => ({
  default: Object.assign((selector: (state: typeof chatState) => unknown) => selector(chatState), {
    getState: () => chatState,
  }),
}));
vi.mock('@/hooks/message-input/useInputHistory', () => ({ addInputHistory: vi.fn() }));

import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { GoalStatusCard } from '../GoalStatusCard';

const goalPayload = (objective: string) => ({
  goal_id: `goal-${objective}`,
  objective,
  status: 'active',
  tokens_used: 0,
  time_used_seconds: 0,
});

type Reply = { ok: boolean; json: () => Promise<unknown>; text: () => Promise<string> };
const json = (body: unknown): Reply => ({ ok: true, json: async () => body, text: async () => JSON.stringify(body) });

/** Holds every `/status` reply until the test releases it, so a reply can arrive after the chat was switched. */
function holdStatusReplies() {
  const held = new Map<string, (reply: Reply) => void>();
  fetchMock.mockImplementation(
    (url: string) =>
      new Promise<Reply>((resolve) => {
        if (url.endsWith('/status')) {
          held.set(url, resolve);
        } else {
          resolve(json({}));
        }
      }),
  );
  return async (chatId: string, body: unknown) => {
    await act(async () => {
      held.get(`/goals/${chatId}/status`)?.(json(body));
      await new Promise((settled) => setTimeout(settled, 0));
    });
  };
}

const openChat = (chatId: string) => {
  chatState.chatId = chatId;
};

describe('GoalStatusCard across chats', () => {
  beforeAll(async () => {
    await import('@/store/chat/messageStream/streamHelpers');
  });

  beforeEach(() => {
    fetchMock.mockReset();
    useGoalStore.getState().bindChat(null);
    openChat('chat-a');
  });

  it('shows the goal of the open chat, and nothing of the previous chat once another is opened', async () => {
    const release = holdStatusReplies();
    const { rerender } = render(<GoalStatusCard />);
    await release('chat-a', { goal: goalPayload('Goal of A') });
    expect(await screen.findByTestId('goal-status-header')).toBeTruthy();

    openChat('chat-b');
    rerender(<GoalStatusCard />);

    expect(screen.queryByTestId('goal-status-header')).toBeNull();
    await release('chat-b', { goal: null });
    expect(screen.queryByTestId('goal-status-header')).toBeNull();
  });

  it('is not taken over by a slow reply to the previous chat, and then shows the goal of the new chat', async () => {
    const release = holdStatusReplies();
    const { rerender } = render(<GoalStatusCard />);
    openChat('chat-b');
    rerender(<GoalStatusCard />);

    await release('chat-a', { goal: goalPayload('Goal of A') });
    expect(screen.queryByTestId('goal-status-header')).toBeNull();

    await release('chat-b', { goal: goalPayload('Goal of B') });
    await waitFor(() => expect(useGoalStore.getState().activeGoal?.objective).toBe('Goal of B'));
    expect(await screen.findByTestId('goal-status-header')).toBeTruthy();
  });

  it('ignores a goal that a background notification reports for a chat that is not open', async () => {
    const release = holdStatusReplies();
    render(<GoalStatusCard />);
    await release('chat-a', { goal: goalPayload('Goal of A') });
    await screen.findByTestId('goal-status-header');

    fetchMock.mockImplementation(async () => json({ goal: goalPayload('Goal of C') }));
    await act(async () => {
      await useGoalStore.getState().refreshActiveGoal('chat-c');
    });

    expect(useGoalStore.getState().activeGoal?.objective).toBe('Goal of A');
  });
});
