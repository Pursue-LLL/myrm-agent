/**
 * Real scenario: a goal runs in chat A, the user opens chat B. B must never show A's goal, not for a frame and not when
 * a slow reply to A's requests arrives afterwards; B's own goal then takes the slot.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));

import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { useGoalSync } from '../useGoalSync';

const json = (body: unknown) => ({ ok: true, json: async () => body, text: async () => JSON.stringify(body) });

const goalPayload = (objective: string) => ({
  goal_id: `goal-${objective}`,
  objective,
  status: 'active',
  tokens_used: 0,
  time_used_seconds: 0,
});

/** Answers each request of the sync by hand so a reply can arrive after the chat was switched. */
function mockServer() {
  const waiting = new Map<string, (value: ReturnType<typeof json>) => void>();
  fetchMock.mockImplementation(
    (url: string) =>
      new Promise((resolve) => {
        waiting.set(url, resolve);
      }),
  );
  return {
    answer: async (url: string, body: unknown) => {
      await act(async () => {
        waiting.get(url)?.(json(body));
        // The store applies a goal after a dynamic import: let it settle before the test looks.
        await new Promise((settled) => setTimeout(settled, 0));
      });
    },
    requested: (url: string) => waiting.has(url),
  };
}

const objectiveOf = () => useGoalStore.getState().activeGoal?.objective;

describe('useGoalSync', () => {
  beforeAll(async () => {
    await import('@/store/chat/messageStream/streamHelpers');
  });

  beforeEach(() => {
    fetchMock.mockReset();
    useGoalStore.getState().bindChat(null);
  });

  it('loads the goal and the queue of the chat it is mounted for', async () => {
    const server = mockServer();
    renderHook(() => useGoalSync('chat-a'));

    expect(useGoalStore.getState().chatId).toBe('chat-a');
    await server.answer('/goals/chat-a/status', { goal: goalPayload('Goal of A') });
    await server.answer('/goals/chat-a/queue', {
      queue: [{ goal_id: 'q1', objective: 'Next in A', priority: 1, status: 'queued' }],
    });

    expect(objectiveOf()).toBe('Goal of A');
    expect(useGoalStore.getState().queuedGoals.map((g) => g.objective)).toEqual(['Next in A']);
  });

  it('empties the slot the moment another chat is opened, before anything is loaded for it', async () => {
    const server = mockServer();
    const { rerender } = renderHook(({ chatId }) => useGoalSync(chatId), { initialProps: { chatId: 'chat-a' } });
    await server.answer('/goals/chat-a/status', { goal: goalPayload('Goal of A') });
    expect(objectiveOf()).toBe('Goal of A');

    rerender({ chatId: 'chat-b' });

    expect(useGoalStore.getState().chatId).toBe('chat-b');
    expect(useGoalStore.getState().activeGoal).toBeNull();
    expect(server.requested('/goals/chat-b/status')).toBe(true);
  });

  it('drops a slow reply for the old chat and then shows the goal of the new one', async () => {
    const server = mockServer();
    const { rerender } = renderHook(({ chatId }) => useGoalSync(chatId), { initialProps: { chatId: 'chat-a' } });
    rerender({ chatId: 'chat-b' });

    await server.answer('/goals/chat-a/status', { goal: goalPayload('Goal of A') });
    expect(useGoalStore.getState().activeGoal).toBeNull();

    await server.answer('/goals/chat-b/status', { goal: goalPayload('Goal of B') });
    expect(objectiveOf()).toBe('Goal of B');
  });

  it('leaves the slot empty for a chat that has no goal', async () => {
    const server = mockServer();
    const { rerender } = renderHook(({ chatId }) => useGoalSync(chatId), { initialProps: { chatId: 'chat-a' } });
    await server.answer('/goals/chat-a/status', { goal: goalPayload('Goal of A') });

    rerender({ chatId: 'chat-b' });
    await server.answer('/goals/chat-b/status', { goal: null });

    expect(useGoalStore.getState().activeGoal).toBeNull();
  });

  it('unbinds and requests nothing while no chat is open', () => {
    const { rerender } = renderHook(({ chatId }) => useGoalSync(chatId), {
      initialProps: { chatId: 'chat-a' as string | null },
    });
    fetchMock.mockClear();

    rerender({ chatId: null });

    expect(useGoalStore.getState().chatId).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
