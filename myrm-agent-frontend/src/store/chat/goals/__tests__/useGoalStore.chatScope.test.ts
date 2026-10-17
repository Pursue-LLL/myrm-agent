/**
 * The goal store holds the goal of exactly one chat: the chat it was last bound to.
 *
 * Real scenario: a goal runs in chat A while the user works in chat B. Whatever arrives for A - a stream event, a
 * background-job notification, a slow reply to a request made before switching - must not land in the slot B shows.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock } = vi.hoisted(() => ({ fetchMock: vi.fn() }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));

import { useGoalStore } from '../useGoalStore';
import { normalizeGoalState } from '@/store/chat/messageStream/streamHelpers';

const goalOf = (objective: string) =>
  normalizeGoalState({
    goal_id: `goal-${objective}`,
    objective,
    status: 'active',
    tokens_used: 0,
    time_used_seconds: 0,
  });

const goalPayload = (objective: string) => ({
  goal_id: `goal-${objective}`,
  objective,
  status: 'active',
  tokens_used: 0,
  time_used_seconds: 0,
});

const json = (body: unknown, ok = true) => ({ ok, json: async () => body, text: async () => JSON.stringify(body) });

/** A request the test answers by hand, so a reply can arrive after the user has moved on. */
function pendingReply() {
  let answer: (value: ReturnType<typeof json>) => void = () => undefined;
  const reply = new Promise<ReturnType<typeof json>>((resolve) => {
    answer = resolve;
  });
  return { reply, answer };
}

const objectiveOf = () => useGoalStore.getState().activeGoal?.objective;

describe('useGoalStore chat scope', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    useGoalStore.getState().bindChat(null);
    useGoalStore.getState().bindChat('chat-a');
  });

  describe('bindChat', () => {
    it('empties the goal, the queue and the branch when another chat is opened', () => {
      const store = useGoalStore.getState();
      store.setActiveGoal('chat-a', goalOf('Goal of A'));
      store.setGitBranch('chat-a', 'feature/a');
      useGoalStore.setState({ queuedGoals: [{ goal_id: 'q1', objective: 'Next', priority: 1, status: 'queued' }] });

      store.bindChat('chat-b');

      const next = useGoalStore.getState();
      expect(next.chatId).toBe('chat-b');
      expect(next.activeGoal).toBeNull();
      expect(next.gitBranch).toBeNull();
      expect(next.queuedGoals).toEqual([]);
    });

    it('keeps everything when the chat that is already bound is bound again', () => {
      useGoalStore.getState().setActiveGoal('chat-a', goalOf('Goal of A'));

      useGoalStore.getState().bindChat('chat-a');

      expect(objectiveOf()).toBe('Goal of A');
    });

    it('empties the slot when no chat is open', () => {
      useGoalStore.getState().setActiveGoal('chat-a', goalOf('Goal of A'));

      useGoalStore.getState().bindChat(null);

      expect(useGoalStore.getState().chatId).toBeNull();
      expect(useGoalStore.getState().activeGoal).toBeNull();
    });
  });

  describe('writes tagged with a chat', () => {
    it('drop what belongs to another chat', () => {
      const store = useGoalStore.getState();
      store.setActiveGoal('chat-a', goalOf('Goal of A'));

      store.setActiveGoal('chat-b', goalOf('Goal of B'));
      store.updateGoalStatus('chat-b', 'cancelled');
      store.setGitBranch('chat-b', 'feature/b');

      expect(objectiveOf()).toBe('Goal of A');
      expect(useGoalStore.getState().activeGoal?.status).toBe('active');
      expect(useGoalStore.getState().gitBranch).toBeNull();
    });

    it('apply what belongs to the bound chat', () => {
      const store = useGoalStore.getState();
      store.setActiveGoal('chat-a', goalOf('Goal of A'));

      store.updateGoalStatus('chat-a', 'paused', 'Waiting for a decision');

      expect(useGoalStore.getState().activeGoal).toMatchObject({ status: 'paused', reason: 'Waiting for a decision' });
    });

    it('ignore a write whose source could not name its chat', () => {
      const store = useGoalStore.getState();
      store.setActiveGoal('chat-a', goalOf('Goal of A'));

      store.setActiveGoal('', goalOf('Goal of nobody'));
      store.updateGoalStatus('', 'cancelled');
      store.setGitBranch('', 'feature/nobody');

      expect(objectiveOf()).toBe('Goal of A');
      expect(useGoalStore.getState().activeGoal?.status).toBe('active');
      expect(useGoalStore.getState().gitBranch).toBeNull();
    });
  });

  describe('replies that arrive after another chat was opened', () => {
    it('refreshActiveGoal does not put the goal of the old chat into the new one', async () => {
      const slow = pendingReply();
      fetchMock.mockReturnValueOnce(slow.reply);
      const refreshing = useGoalStore.getState().refreshActiveGoal('chat-a');

      useGoalStore.getState().bindChat('chat-b');
      slow.answer(json({ goal: goalPayload('Goal of A') }));
      await refreshing;

      expect(useGoalStore.getState().activeGoal).toBeNull();
    });

    it('refreshActiveGoal for a chat that is not the open one never touches the slot', async () => {
      useGoalStore.getState().setActiveGoal('chat-a', goalOf('Goal of A'));
      fetchMock.mockResolvedValueOnce(json({ goal: goalPayload('Goal of C') }));

      await useGoalStore.getState().refreshActiveGoal('chat-c');

      expect(objectiveOf()).toBe('Goal of A');
    });

    it('refreshActiveGoal keeps the current goal when the server has none', async () => {
      useGoalStore.getState().setActiveGoal('chat-a', goalOf('Goal of A'));
      fetchMock.mockResolvedValueOnce(json({ goal: null }));

      await useGoalStore.getState().refreshActiveGoal('chat-a');

      expect(objectiveOf()).toBe('Goal of A');
    });

    it('fetchQueue does not put the queue of another chat into the open one', async () => {
      fetchMock.mockResolvedValueOnce(
        json({ queue: [{ goal_id: 'q1', objective: 'Queued in D', priority: 1, status: 'queued' }] }),
      );

      await useGoalStore.getState().fetchQueue('chat-d');

      expect(useGoalStore.getState().queuedGoals).toEqual([]);
    });

    it('fetchQueue fills the queue of the open chat', async () => {
      fetchMock.mockResolvedValueOnce(
        json({ queue: [{ goal_id: 'q1', objective: 'Queued in A', priority: 1, status: 'queued' }] }),
      );

      await useGoalStore.getState().fetchQueue('chat-a');

      expect(useGoalStore.getState().queuedGoals.map((g) => g.objective)).toEqual(['Queued in A']);
    });

    it('updateObjective does not rewrite the goal of the chat that is open now', async () => {
      const slow = pendingReply();
      fetchMock.mockReturnValueOnce(slow.reply);
      const saving = useGoalStore.getState().updateObjective('chat-a', 'Renamed in A');

      useGoalStore.getState().bindChat('chat-b');
      useGoalStore.getState().setActiveGoal('chat-b', goalOf('Goal of B'));
      slow.answer(json({}));
      await saving;

      expect(objectiveOf()).toBe('Goal of B');
    });

    it('updateGoalBudget does not rewrite the budget of the chat that is open now', async () => {
      const slow = pendingReply();
      fetchMock.mockReturnValueOnce(slow.reply);
      const topping = useGoalStore.getState().updateGoalBudget('chat-a', 10_000);

      useGoalStore.getState().bindChat('chat-b');
      useGoalStore.getState().setActiveGoal('chat-b', goalOf('Goal of B'));
      const budgetBefore = useGoalStore.getState().activeGoal?.budget;
      slow.answer(json({ new_budget: { max_tokens: 99_999 } }));
      await topping;

      expect(useGoalStore.getState().activeGoal?.budget).toEqual(budgetBefore);
    });

    it('cancelQueuedGoal leaves the queue of the chat that is open now alone', async () => {
      const slow = pendingReply();
      fetchMock.mockReturnValueOnce(slow.reply);
      const cancelling = useGoalStore.getState().cancelQueuedGoal('chat-a', 'q1');

      useGoalStore.getState().bindChat('chat-b');
      useGoalStore.setState({
        queuedGoals: [{ goal_id: 'q1', objective: 'Queued in B', priority: 1, status: 'queued' }],
      });
      slow.answer(json({}));
      await cancelling;

      expect(useGoalStore.getState().queuedGoals.map((g) => g.goal_id)).toEqual(['q1']);
    });
  });

  describe('reorderQueue', () => {
    const queued = (id: string) => ({ goal_id: id, objective: id, priority: 1, status: 'queued' });

    it('shows the new order at once and tells the server', async () => {
      useGoalStore.setState({ queuedGoals: [queued('q1'), queued('q2'), queued('q3')] });
      fetchMock.mockResolvedValue(json({}));

      const reordering = useGoalStore.getState().reorderQueue('chat-a', ['q3', 'q1', 'q2']);

      expect(useGoalStore.getState().queuedGoals.map((g) => g.goal_id)).toEqual(['q3', 'q1', 'q2']);
      await reordering;
      expect(fetchMock).toHaveBeenCalledWith(
        '/goals/chat-a/queue/reorder',
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ ordered_goal_ids: ['q3', 'q1', 'q2'] }) }),
      );
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    describe('when the server does not take the new order', () => {
      const serverOrder = [queued('q1'), queued('q2'), queued('q3')];
      const idsInQueue = () => useGoalStore.getState().queuedGoals.map((g) => g.goal_id);

      beforeEach(() => {
        useGoalStore.setState({ queuedGoals: serverOrder });
      });

      it('shows the order the server still has after a refusal', async () => {
        fetchMock.mockImplementation(async (url: string) =>
          url.endsWith('/reorder') ? json({}, false) : json({ queue: serverOrder }),
        );

        await useGoalStore.getState().reorderQueue('chat-a', ['q3', 'q1', 'q2']);

        expect(idsInQueue()).toEqual(['q1', 'q2', 'q3']);
      });

      it('shows the order the server still has after a network failure', async () => {
        fetchMock.mockImplementation(async (url: string) => {
          if (url.endsWith('/reorder')) {
            throw new Error('network down');
          }
          return json({ queue: serverOrder });
        });

        await useGoalStore.getState().reorderQueue('chat-a', ['q3', 'q1', 'q2']);

        expect(idsInQueue()).toEqual(['q1', 'q2', 'q3']);
      });
    });
  });
});
