import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { AgentConfig } from '@/store/chat/types';
import { QUEUE_DRAIN_DELAYS_MS, useMessageQueueStore } from '@/store/chat/useMessageQueueStore';
import useChatStore from '@/store/useChatStore';
import { useQueueDrain } from '../useQueueDrain';

const CHAT = 'chat-1';

const mocks = vi.hoisted(() => ({
  sendMessage: vi.fn<(...args: unknown[]) => Promise<boolean>>(),
  setInputMessage: vi.fn(),
  setFiles: vi.fn(),
  setPendingArchiveRestoreActions: vi.fn(),
  toastError: vi.fn(),
  overrideApplied: vi.fn(),
  overrideNoop: vi.fn(),
  busyRequeued: vi.fn(),
  sendFailed: vi.fn(),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: (...args: unknown[]) => mocks.toastError(...args) },
}));

vi.mock('@/services/turnCapabilityMetrics', () => ({
  recordTurnCapabilityOverrideApplied: (...args: unknown[]) => mocks.overrideApplied(...args),
  recordTurnCapabilityOverrideNoop: (...args: unknown[]) => mocks.overrideNoop(...args),
  recordTurnCapabilityBusyRequeued: (...args: unknown[]) => mocks.busyRequeued(...args),
  recordTurnCapabilitySendFailed: (...args: unknown[]) => mocks.sendFailed(...args),
  recordTurnCapabilitySelectionSubmitted: vi.fn(),
  recordTurnCapabilityQueueEnqueued: vi.fn(),
}));

vi.mock('@/store/useChatStore', async () => {
  const { create } = await import('zustand');
  const useChatStore = create(() => ({
    chatId: 'chat-1' as string | null,
    loading: false,
    agentConfig: null as Record<string, unknown> | null,
    sendMessage: (...args: unknown[]) => mocks.sendMessage(...args),
    setInputMessage: (...args: unknown[]) => mocks.setInputMessage(...args),
    setFiles: (...args: unknown[]) => mocks.setFiles(...args),
    setPendingArchiveRestoreActions: (...args: unknown[]) => mocks.setPendingArchiveRestoreActions(...args),
  }));
  return { default: useChatStore };
});

const store = () => useMessageQueueStore.getState();
const agentWithSkills = (): AgentConfig => ({
  selectedSkillIds: ['skill-a', 'skill-b'],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: false,
});
const queued = () => store().queues[CHAT]?.items.map((item) => item.text) ?? [];
const sentTexts = () => mocks.sendMessage.mock.calls.map((call) => call[0]);

function enqueue(...texts: string[]): void {
  act(() => {
    texts.forEach((text) => store().enqueue(CHAT, { text, files: [] }));
  });
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function busyError(): Error {
  const error = new Error('Agent is busy');
  error.name = 'AgentBusyError';
  return error;
}

/** A turn that stays in flight until the test ends it, like a real stream. */
function holdTurnOpen(): { finish: () => Promise<void> } {
  let resolveTurn: (dispatched: boolean) => void = () => undefined;
  mocks.sendMessage.mockImplementationOnce(
    () =>
      new Promise<boolean>((resolve) => {
        resolveTurn = resolve;
        useChatStore.setState({ loading: true });
      }),
  );
  return {
    finish: async () => {
      await act(async () => {
        useChatStore.setState({ loading: false });
        resolveTurn(true);
        await Promise.resolve();
      });
    },
  };
}

describe('useQueueDrain', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useMessageQueueStore.setState({ queues: {} });
    useChatStore.setState({ chatId: CHAT, loading: false, agentConfig: null });
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.sendMessage.mockResolvedValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends a queued message once the agent is idle, handing over its own attachments', async () => {
    const files = [{ id: 'file-1', name: 'notes.zip', status: 'done' }];
    renderHook(() => useQueueDrain(CHAT));
    act(() => {
      store().enqueue(CHAT, { text: 'with files', files: files as never, archiveRestoreActions: undefined });
    });

    await advance(QUEUE_DRAIN_DELAYS_MS[0]);

    expect(mocks.sendMessage).toHaveBeenCalledWith(
      'with files',
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      true,
      undefined,
      { files },
    );
    expect(queued()).toEqual([]);
  });

  it('sends the messages one at a time, each only after the previous turn ended', async () => {
    renderHook(() => useQueueDrain(CHAT));
    const firstTurn = holdTurnOpen();
    enqueue('first', 'second');

    await advance(QUEUE_DRAIN_DELAYS_MS[0]);
    expect(sentTexts()).toEqual(['first']);

    await advance(30_000);
    expect(sentTexts()).toEqual(['first']);
    expect(queued()).toEqual(['second']);

    await firstTurn.finish();
    await advance(QUEUE_DRAIN_DELAYS_MS[0]);
    expect(sentTexts()).toEqual(['first', 'second']);
  });

  it('waits while the agent is busy and starts after it went idle', async () => {
    useChatStore.setState({ loading: true });
    renderHook(() => useQueueDrain(CHAT));
    enqueue('after the turn');

    await advance(5_000);
    expect(mocks.sendMessage).not.toHaveBeenCalled();

    act(() => useChatStore.setState({ loading: false }));
    await advance(QUEUE_DRAIN_DELAYS_MS[0]);
    expect(sentTexts()).toEqual(['after the turn']);
  });

  it('cancels the pending send when the agent becomes busy again inside the delay window', async () => {
    renderHook(() => useQueueDrain(CHAT));
    enqueue('raced');

    await advance(QUEUE_DRAIN_DELAYS_MS[0] - 100);
    act(() => useChatStore.setState({ loading: true }));
    await advance(1_000);

    expect(mocks.sendMessage).not.toHaveBeenCalled();
    expect(queued()).toEqual(['raced']);
  });

  it('never sends into a chat other than the active one', async () => {
    useChatStore.setState({ chatId: 'another-chat' });
    renderHook(() => useQueueDrain(CHAT));
    enqueue('for chat-1');

    await advance(60_000);

    expect(mocks.sendMessage).not.toHaveBeenCalled();
    expect(queued()).toEqual(['for chat-1']);
  });

  it('does nothing without a chat and stops when unmounted', async () => {
    const idle = renderHook(() => useQueueDrain(null));
    const mounted = renderHook(() => useQueueDrain(CHAT));
    enqueue('still waiting');
    idle.unmount();
    mounted.unmount();

    await advance(60_000);

    expect(mocks.sendMessage).not.toHaveBeenCalled();
  });

  it('does not send while paused after Stop, and continues after resume', async () => {
    renderHook(() => useQueueDrain(CHAT));
    enqueue('follow-up');
    act(() => store().pauseOnStop(CHAT));

    await advance(60_000);
    expect(mocks.sendMessage).not.toHaveBeenCalled();

    act(() => store().resume(CHAT));
    await advance(QUEUE_DRAIN_DELAYS_MS[0]);
    expect(sentTexts()).toEqual(['follow-up']);
  });

  it('leaves the message that is being edited alone', async () => {
    renderHook(() => useQueueDrain(CHAT));
    enqueue('under edit');
    const id = store().queues[CHAT].items[0].id;
    act(() => store().setEditingId(CHAT, id));

    await advance(60_000);
    expect(mocks.sendMessage).not.toHaveBeenCalled();

    act(() => store().setEditingId(CHAT, null));
    await advance(QUEUE_DRAIN_DELAYS_MS[0]);
    expect(sentTexts()).toEqual(['under edit']);
  });

  describe('when the server is still busy', () => {
    it('requeues the message and retries along the backoff ladder', async () => {
      mocks.sendMessage.mockRejectedValueOnce(busyError());
      renderHook(() => useQueueDrain(CHAT));
      enqueue('persistent');

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);
      expect(mocks.sendMessage).toHaveBeenCalledTimes(1);
      expect(queued()).toEqual(['persistent']);

      await advance(QUEUE_DRAIN_DELAYS_MS[1] - 1);
      expect(mocks.sendMessage).toHaveBeenCalledTimes(1);

      await advance(1);
      expect(mocks.sendMessage).toHaveBeenCalledTimes(2);
      expect(queued()).toEqual([]);
      expect(store().queues[CHAT].failedAttempts).toBe(0);
    });

    it('stops retrying after the ladder is used up, tells the user and keeps the message', async () => {
      mocks.sendMessage.mockRejectedValue(busyError());
      renderHook(() => useQueueDrain(CHAT));
      enqueue('never accepted');

      await advance(QUEUE_DRAIN_DELAYS_MS.reduce((total, delay) => total + delay, 0));
      expect(mocks.sendMessage).toHaveBeenCalledTimes(QUEUE_DRAIN_DELAYS_MS.length);
      expect(store().queues[CHAT].pausedReason).toBe('stuck');
      expect(mocks.toastError).toHaveBeenCalledTimes(1);
      expect(mocks.toastError).toHaveBeenCalledWith('queue.stuck');

      await advance(120_000);
      expect(mocks.sendMessage).toHaveBeenCalledTimes(QUEUE_DRAIN_DELAYS_MS.length);
      expect(queued()).toEqual(['never accepted']);
    });

    it('retries from the first step after the user resumes a stuck queue', async () => {
      mocks.sendMessage.mockRejectedValue(busyError());
      renderHook(() => useQueueDrain(CHAT));
      enqueue('retry me');
      await advance(QUEUE_DRAIN_DELAYS_MS.reduce((total, delay) => total + delay, 0));
      expect(store().queues[CHAT].pausedReason).toBe('stuck');

      mocks.sendMessage.mockReset();
      mocks.sendMessage.mockResolvedValue(true);
      act(() => store().resume(CHAT));
      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(sentTexts()).toEqual(['retry me']);
      expect(queued()).toEqual([]);
    });

    it('records the busy requeue for a message that carried a capability selection', async () => {
      mocks.sendMessage.mockRejectedValueOnce(busyError());
      renderHook(() => useQueueDrain(CHAT));
      act(() => {
        store().enqueue(CHAT, {
          text: 'scoped',
          files: [],
          turnCapabilitySelection: { skillIds: ['skill-a'], mcpNames: null },
        });
      });

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(mocks.busyRequeued).toHaveBeenCalledWith('queue_drain', 'chat:chat-1');
    });
  });

  describe('when the request is refused locally', () => {
    it('keeps the message, pauses the queue and does not retry on its own', async () => {
      mocks.sendMessage.mockResolvedValue(false);
      renderHook(() => useQueueDrain(CHAT));
      enqueue('no model selected', 'next');

      await advance(120_000);

      expect(mocks.sendMessage).toHaveBeenCalledTimes(1);
      expect(queued()).toEqual(['no model selected', 'next']);
      expect(store().queues[CHAT].pausedReason).toBe('stuck');
      expect(mocks.toastError).not.toHaveBeenCalled();
    });
  });

  describe('when the turn fails after it was dispatched', () => {
    it('moves on to the next message instead of resending the failed one', async () => {
      mocks.sendMessage.mockRejectedValueOnce(new Error('upstream exploded'));
      renderHook(() => useQueueDrain(CHAT));
      enqueue('fails', 'next');

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);
      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(sentTexts()).toEqual(['fails', 'next']);
      expect(queued()).toEqual([]);
    });

    it('hands an invalid archive restore back to the composer', async () => {
      const { FatalNetworkError, ARCHIVE_RESTORE_ACTION_INVALID } = await import('@/lib/utils/networkResilience');
      const files = [{ id: 'file-1', name: 'notes.zip', status: 'done' }];
      const restoreActions = [{ type: 'archive_restore' as const, restoreArg: '.context/a/result.txt:1-2' }];
      mocks.sendMessage.mockRejectedValueOnce(
        new FatalNetworkError('invalid restore', { status: 400, errorCode: ARCHIVE_RESTORE_ACTION_INVALID }),
      );
      renderHook(() => useQueueDrain(CHAT));
      act(() => {
        store().enqueue(CHAT, {
          text: 'restore please',
          files: files as never,
          archiveRestoreActions: restoreActions,
        });
      });

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(mocks.setInputMessage).toHaveBeenCalledWith('restore please');
      expect(mocks.setFiles).toHaveBeenCalledWith(files);
      expect(mocks.setPendingArchiveRestoreActions).toHaveBeenCalledWith(restoreActions);
      expect(queued()).toEqual([]);
    });

    it('reports network failures of a capability-scoped message', async () => {
      const networkError = new Error('network timeout');
      networkError.name = 'TypeError';
      mocks.sendMessage.mockRejectedValueOnce(networkError);
      useChatStore.setState({ agentConfig: agentWithSkills() });
      renderHook(() => useQueueDrain(CHAT));
      act(() => {
        store().enqueue(CHAT, {
          text: 'scoped',
          files: [],
          turnCapabilitySelection: { skillIds: ['skill-b'], mcpNames: null },
        });
      });

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(mocks.sendFailed).toHaveBeenCalledWith('queue_drain', 'network_error', 'chat:chat-1');
    });
  });

  describe('capability override', () => {
    it('sends a queued capability selection as the turn override and reports it once dispatched', async () => {
      useChatStore.setState({ agentConfig: agentWithSkills() });
      renderHook(() => useQueueDrain(CHAT));
      act(() => {
        store().enqueue(CHAT, {
          text: 'scoped',
          files: [],
          turnCapabilitySelection: { skillIds: ['skill-b'], mcpNames: null },
        });
      });

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(mocks.sendMessage).toHaveBeenCalledWith(
        'scoped',
        undefined,
        undefined,
        undefined,
        undefined,
        expect.objectContaining({ selectedSkillIds: ['skill-b'] }),
        true,
        { source: 'queue_drain', effectiveSkillCount: 1, effectiveMcpCount: 0 },
        { files: [] },
      );
      expect(mocks.overrideApplied).toHaveBeenCalledTimes(1);
    });

    it('does not count a refused request as an applied override', async () => {
      mocks.sendMessage.mockResolvedValue(false);
      useChatStore.setState({ agentConfig: agentWithSkills() });
      renderHook(() => useQueueDrain(CHAT));
      act(() => {
        store().enqueue(CHAT, {
          text: 'scoped',
          files: [],
          turnCapabilitySelection: { skillIds: ['skill-b'], mcpNames: null },
        });
      });

      await advance(QUEUE_DRAIN_DELAYS_MS[0]);

      expect(mocks.overrideApplied).not.toHaveBeenCalled();
    });
  });
});
