import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { CompactResult } from '@/services/contextCompaction';

const kit = vi.hoisted(() => ({
  chat: {
    chatId: 'chat-1' as string | null,
    loadMessages: vi.fn<(chatId: string) => Promise<void>>(),
    resetSessionState: vi.fn<() => void>(),
    stopMessage: vi.fn<() => void>(),
  },
  runManualCompaction: vi.fn<(chatId: string, focusTopic?: string) => Promise<CompactResult>>(),
  focusFlushChat: vi.fn<(chatId: string) => Promise<{ cleared: boolean }>>(),
  showToast: vi.fn(),
  loadingToast: vi.fn(() => 'loading-toast'),
  dismissToast: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({ default: { getState: () => kit.chat } }));
vi.mock('@/services/contextCompaction', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/contextCompaction')>()),
  runManualCompaction: kit.runManualCompaction,
}));
vi.mock('@/services/chat', () => ({ focusFlushChat: kit.focusFlushChat }));
vi.mock('@/services/i18nToastService', () => ({ showI18nToast: kit.showToast }));
vi.mock('sonner', () => ({ toast: { loading: kit.loadingToast, dismiss: kit.dismissToast } }));

import { executeCompactSlashCommand, executeFocusSlashCommand } from '../contextSlashCommands';

const DONE = { success: true, newInputValue: '' };
const NO_CHAT = { success: false, error: 'No active chat' };

const compacted: CompactResult = { compacted: true, message_count: 12, tokens_saved: 3400, reason: null };

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.removeItem('dontRemindCompact');
  kit.chat.chatId = 'chat-1';
  kit.chat.loadMessages.mockResolvedValue(undefined);
  kit.runManualCompaction.mockResolvedValue(compacted);
  kit.focusFlushChat.mockResolvedValue({ cleared: true });
});

describe('executeCompactSlashCommand', () => {
  it('does nothing without an active chat', async () => {
    kit.chat.chatId = null;

    await expect(executeCompactSlashCommand('/compact')).resolves.toEqual(NO_CHAT);

    expect(kit.runManualCompaction).not.toHaveBeenCalled();
    expect(kit.loadingToast).not.toHaveBeenCalled();
  });

  it.each([
    { input: '/compact auth flow', topic: 'auth flow' },
    { input: '/compact   spaced  ', topic: 'spaced' },
    { input: '/compact', topic: undefined },
  ])('compresses with the topic typed after the command: $input', async ({ input, topic }) => {
    await expect(executeCompactSlashCommand(input)).resolves.toEqual(DONE);

    expect(kit.runManualCompaction).toHaveBeenCalledWith('chat-1', topic);
  });

  it('reports what the compression saved and leaves the transcript to the store sync', async () => {
    await executeCompactSlashCommand('/compact');

    expect(kit.showToast).toHaveBeenCalledWith(
      'commands.builtin.compacted',
      { messageCount: 12, tokensSaved: 3400 },
      { type: 'success' },
    );
    expect(kit.dismissToast).toHaveBeenCalledWith('loading-toast');
    expect(kit.chat.loadMessages).not.toHaveBeenCalled();
  });

  it.each([
    { reason: 'no_compactable_messages', copy: 'chat.compact.skip.nothing', type: 'info' },
    { reason: 'concurrent_compaction_in_progress', copy: 'chat.compact.skip.busy', type: 'info' },
    { reason: 'summarize_circuit_open', copy: 'chat.compact.skip.paused', type: 'warning' },
    { reason: 'compression_anti_thrash_active', copy: 'chat.compact.skip.ineffective', type: 'warning' },
  ])('words a compression the server did not run for its reason: $reason', async ({ reason, copy, type }) => {
    kit.runManualCompaction.mockResolvedValue({ ...compacted, compacted: false, reason });

    await expect(executeCompactSlashCommand('/compact')).resolves.toEqual(DONE);

    expect(kit.showToast).toHaveBeenCalledWith(copy, undefined, { type });
    expect(kit.dismissToast).toHaveBeenCalledWith('loading-toast');
    expect(kit.chat.loadMessages).not.toHaveBeenCalled();
  });

  it('reports a failure the server returned as a failed compression, without the raw reason', async () => {
    kit.runManualCompaction.mockResolvedValue({ ...compacted, compacted: false, reason: 'timeout: summarizer 60s' });

    await expect(executeCompactSlashCommand('/compact')).resolves.toEqual({
      success: false,
      error: 'Compaction failed',
    });

    expect(kit.showToast).toHaveBeenCalledWith('chat.compact.failed', undefined, { type: 'error' });
  });

  it('reports a request that failed', async () => {
    kit.runManualCompaction.mockRejectedValue(new Error('server error'));

    await expect(executeCompactSlashCommand('/compact')).resolves.toEqual({
      success: false,
      error: 'Compaction failed',
    });

    expect(kit.showToast).toHaveBeenCalledWith('chat.compact.failed', undefined, { type: 'error' });
    expect(kit.dismissToast).toHaveBeenCalledWith('loading-toast');
    expect(kit.chat.loadMessages).not.toHaveBeenCalled();
  });

  it.each([
    { stored: null, reminded: true },
    { stored: 'true', reminded: false },
  ])(
    'warns that a manual compaction clears the prompt cache unless dismissed for good (stored: $stored)',
    async ({ stored, reminded }) => {
      if (stored) {
        localStorage.setItem('dontRemindCompact', stored);
      }

      await executeCompactSlashCommand('/compact');

      const reminder = kit.showToast.mock.calls.find(([key]) => key === 'commands.builtin.compactToast');
      expect(reminder !== undefined).toBe(reminded);
    },
  );
});

describe('executeFocusSlashCommand', () => {
  it('does nothing without an active chat', async () => {
    kit.chat.chatId = null;

    await expect(executeFocusSlashCommand()).resolves.toEqual(NO_CHAT);

    expect(kit.focusFlushChat).not.toHaveBeenCalled();
  });

  it('stops the running turn, clears the history, then resets the session and reloads', async () => {
    await expect(executeFocusSlashCommand()).resolves.toEqual(DONE);

    expect(kit.focusFlushChat).toHaveBeenCalledWith('chat-1');
    expect(kit.showToast).toHaveBeenCalledWith('commands.builtin.focusSuccess', undefined, { type: 'success' });
    expect(kit.chat.resetSessionState).toHaveBeenCalledOnce();
    expect(kit.chat.loadMessages).toHaveBeenCalledWith('chat-1');
    const [stopped] = kit.chat.stopMessage.mock.invocationCallOrder;
    const [flushed] = kit.focusFlushChat.mock.invocationCallOrder;
    expect(stopped).toBeLessThan(flushed);
  });

  it('keeps the session as it was when the history could not be cleared', async () => {
    kit.focusFlushChat.mockRejectedValue(new Error('server error'));

    await expect(executeFocusSlashCommand()).resolves.toEqual({ success: false, error: 'Focus flush failed' });

    expect(kit.showToast).toHaveBeenCalledWith('commands.builtin.focusFailed', undefined, { type: 'error' });
    expect(kit.dismissToast).toHaveBeenCalledWith('loading-toast');
    expect(kit.chat.resetSessionState).not.toHaveBeenCalled();
  });
});
