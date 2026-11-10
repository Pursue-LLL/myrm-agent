import { describe, expect, it, vi } from 'vitest';
import {
  emit,
  installGlobalEventsLifecycle,
  mocks,
  mountGlobalEvents,
  recordWindowEvents,
  toastMessage,
  toastOptions,
} from './globalEventsTestKit';

describe('useGlobalEvents: goals, subagents and agent config', () => {
  installGlobalEventsLifecycle();

  describe('goals', () => {
    it('goal_terminal celebrates a completed goal and opens its chat from the notification', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();
      const objective = 'x'.repeat(150);

      emit('goal_terminal', { status: 'complete', objective, session_id: 's1' });

      expect(toastMessage(mocks.toast.success)).toBe('goalCompleted');
      expect(toastOptions(mocks.toast.success)).toEqual({
        description: 'x'.repeat(100),
        duration: 8_000,
        dismissible: true,
      });
      const notifyOptions = mocks.notify.mock.calls[0][1] as { onClick?: () => void };
      notifyOptions.onClick?.();
      expect(mocks.router.push).toHaveBeenCalledWith('/chat/s1');
      expect(events().map((event) => event.type)).toEqual(['goal_terminal']);
    });

    it.each([
      ['cancelled', 'goalCancelled'],
      ['budget_limited', 'goalBudgetLimited'],
      ['needs_human_review', 'goalNeedsReview'],
      ['anything-else', 'goalTerminal'],
    ])('goal_terminal %s warns with %s and has no navigation without a session', (status, label) => {
      mountGlobalEvents();

      emit('goal_terminal', { status, objective: 'o' });

      expect(toastMessage(mocks.toast.warning)).toBe(label);
      expect(toastOptions(mocks.toast.warning)).toEqual({ description: 'o', duration: 10_000, dismissible: true });
      expect((mocks.notify.mock.calls[0][1] as { onClick?: () => void }).onClick).toBeUndefined();
    });

    it('goal_dequeued announces the next goal and reloads the session queue', async () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('goal_dequeued', { objective: 'next', session_id: 's2' });
      emit('goal_dequeued', { objective: 'orphan' });
      await vi.dynamicImportSettled();

      expect(toastMessage(mocks.toast.info)).toBe('goalDequeued');
      expect(toastOptions(mocks.toast.info)).toEqual({ description: 'next', duration: 6_000, dismissible: true });
      (mocks.notify.mock.calls[0][1] as { onClick: () => void }).onClick();
      expect(mocks.router.push).toHaveBeenCalledWith('/chat/s2');
      expect(mocks.fetchQueue).toHaveBeenCalledTimes(1);
      expect(mocks.fetchQueue).toHaveBeenCalledWith('s2');
      expect(events().map((event) => event.type)).toEqual(['goal_dequeued', 'goal_dequeued']);
    });
  });

  describe('subagents', () => {
    it('subagent_stale marks the task and warns with the stale duration in minutes', async () => {
      mountGlobalEvents();

      emit('subagent_stale', { task_id: 't1', stale_duration_seconds: 125, wasted_tokens: 900 });
      emit('subagent_stale', {});
      await vi.dynamicImportSettled();

      expect(mocks.markStale).toHaveBeenCalledTimes(1);
      expect(mocks.markStale).toHaveBeenCalledWith('t1', 125, 900);
      expect(toastMessage(mocks.toast.warning)).toBe('subagentStale');
      expect(toastOptions(mocks.toast.warning)).toEqual({
        description: 'subagentStaleDescription',
        duration: 15_000,
        dismissible: true,
      });
      expect(mocks.notify).toHaveBeenCalledWith('subagentStale', {
        body: 'subagentStaleStats',
        fallbackToToast: false,
        onClick: undefined,
      });
    });

    it('subagent_rebind_required tells the user a subagent needs rebinding', () => {
      mountGlobalEvents();

      emit('subagent_rebind_required', {});

      expect(toastMessage(mocks.toast.info)).toBe('subagentRebindRequired');
      expect(toastOptions(mocks.toast.info)).toEqual({ duration: 10_000 });
    });
  });

  describe('agent_config_updated', () => {
    it('refreshes the roster and the bound chat once after the burst settles', async () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('agent_config_updated', { agent_id: 'a1', action: 'updated' });
      await vi.advanceTimersByTimeAsync(300);
      emit('agent_config_updated', { agent_id: 'a1', action: 'updated' });
      await vi.advanceTimersByTimeAsync(499);
      expect(mocks.fetchAgents).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(1);
      await vi.dynamicImportSettled();

      expect(mocks.syncBoundChatAgentConfig).toHaveBeenCalledTimes(1);
      expect(mocks.syncBoundChatAgentConfig).toHaveBeenCalledWith('a1');
      expect(mocks.fetchAgents).toHaveBeenCalledTimes(1);
      expect(mocks.fetchAgents).toHaveBeenCalledWith(true);
      expect(mocks.fetchAgent).not.toHaveBeenCalled();
      expect(events().map((event) => event.type)).toEqual(['agent-config-updated', 'agent-config-updated']);
      expect(mocks.toast.success).not.toHaveBeenCalled();
      expect(mocks.toast.info).not.toHaveBeenCalled();
    });

    it('also reloads the agent detail when it is the selected one', async () => {
      mocks.agentState.selectedAgent = { id: 'a1' };
      mountGlobalEvents();

      emit('agent_config_updated', { agent_id: 'a1' });
      await vi.advanceTimersByTimeAsync(500);
      await vi.dynamicImportSettled();

      expect(mocks.fetchAgent).toHaveBeenCalledWith('a1');
    });

    it('confirms a rollback and offers the agent after a force push', async () => {
      mountGlobalEvents();

      emit('agent_config_updated', { agent_id: 'a1', action: 'rollback' });
      emit('agent_config_updated', { agent_id: 'a2', action: 'force_push' });
      await vi.advanceTimersByTimeAsync(500);
      await vi.dynamicImportSettled();

      expect(toastMessage(mocks.toast.success)).toBe('agentProfileRollbackSuccess');
      expect(toastMessage(mocks.toast.info)).toBe('forcePushReceived');
      expect(toastOptions(mocks.toast.info)).toMatchObject({
        description: 'forcePushRollbackHint',
        duration: 10_000,
        dismissible: true,
      });
      toastOptions(mocks.toast.info).action?.onClick();
      expect(mocks.router.push).toHaveBeenCalledWith('/?agent_id=a2');
      expect(mocks.syncBoundChatAgentConfig.mock.calls.map(([id]) => id)).toEqual(['a1', 'a2']);
    });

    it('only announces created or deleted agents and ignores events without an agent id', async () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      emit('agent_config_updated', { agent_id: 'a1', action: 'created' });
      emit('agent_config_updated', { agent_id: 'a1', action: 'deleted' });
      emit('agent_config_updated', { action: 'updated' });
      await vi.advanceTimersByTimeAsync(1_000);
      await vi.dynamicImportSettled();

      expect(mocks.fetchAgents).not.toHaveBeenCalled();
      expect(mocks.syncBoundChatAgentConfig).not.toHaveBeenCalled();
      expect(events().map((event) => event.type)).toEqual(Array(3).fill('agent-config-updated'));
    });

    it('drops a pending refresh when the hook unmounts', async () => {
      const { unmount } = mountGlobalEvents();

      emit('agent_config_updated', { agent_id: 'a1' });
      unmount();
      await vi.advanceTimersByTimeAsync(1_000);
      await vi.dynamicImportSettled();

      expect(mocks.fetchAgents).not.toHaveBeenCalled();
      expect(mocks.syncBoundChatAgentConfig).not.toHaveBeenCalled();
    });
  });
});
