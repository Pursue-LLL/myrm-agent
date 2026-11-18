import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCompactChat } from '@/hooks/message-input/useCompactChat';

const mockRunManualCompaction = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => ({
  loading: vi.fn(() => 'toast-1'),
  success: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}));

vi.mock('@/services/contextCompaction', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/contextCompaction')>()),
  runManualCompaction: mockRunManualCompaction,
}));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

function renderCompact() {
  return renderHook(() => useCompactChat('chat-1'));
}

describe('useCompactChat', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockRunManualCompaction.mockResolvedValue({ compacted: true, message_count: 8, tokens_saved: 1200, reason: null });
  });

  describe('asking before it compacts', () => {
    it('compacts at once when the reminder was switched off', async () => {
      localStorage.setItem('dontRemindCompact', 'true');
      const { result } = renderCompact();

      await act(async () => {
        await result.current.requestCompact('billing');
      });

      expect(mockRunManualCompaction).toHaveBeenCalledWith('chat-1', 'billing');
      expect(result.current.showCompactConfirm).toBe(false);
    });

    it('opens the confirmation instead of compacting, then compacts with the topic it was asked for', async () => {
      const { result } = renderCompact();

      await act(async () => {
        await result.current.requestCompact('billing');
      });

      expect(result.current.showCompactConfirm).toBe(true);
      expect(mockRunManualCompaction).not.toHaveBeenCalled();

      await act(async () => {
        result.current.confirmCompact();
      });

      expect(mockRunManualCompaction).toHaveBeenCalledTimes(1);
      expect(mockRunManualCompaction).toHaveBeenCalledWith('chat-1', 'billing');
    });

    it('forgets the topic once a confirmation used it', async () => {
      const { result } = renderCompact();
      await act(async () => {
        await result.current.requestCompact('billing');
      });
      await act(async () => {
        result.current.confirmCompact();
      });

      await act(async () => {
        result.current.confirmCompact();
      });

      expect(mockRunManualCompaction).toHaveBeenLastCalledWith('chat-1', undefined);
    });
  });

  describe('compacting', () => {
    it('remembers that the reminder is off once the box was ticked', async () => {
      const { result } = renderCompact();
      act(() => result.current.setDontRemindCompact(true));

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(localStorage.getItem('dontRemindCompact')).toBe('true');
    });

    it('leaves the reminder on when the box was not ticked', async () => {
      const { result } = renderCompact();

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(localStorage.getItem('dontRemindCompact')).toBeNull();
    });

    it('warns and sends nothing when there is no chat', async () => {
      const { result } = renderHook(() => useCompactChat(undefined));

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(toastMock.warning).toHaveBeenCalledWith('compact.noChatId');
      expect(mockRunManualCompaction).not.toHaveBeenCalled();
    });

    it('names the topic the server kept, not the text that was typed', async () => {
      mockRunManualCompaction.mockResolvedValue({
        compacted: true,
        message_count: 8,
        tokens_saved: 1200,
        reason: null,
        focus_topic: 'billing',
      });
      const { result } = renderCompact();

      await act(async () => {
        await result.current.executeCompact('billing and a long tail');
      });

      expect(mockRunManualCompaction).toHaveBeenCalledWith('chat-1', 'billing and a long tail');
      expect(toastMock.success).toHaveBeenCalledWith('compact.success (billing)', { id: 'toast-1' });
    });

    it.each([
      { reason: 'no_compactable_messages', level: 'info', copy: 'chat.compact.skip.nothing' },
      { reason: 'concurrent_compaction_in_progress', level: 'info', copy: 'chat.compact.skip.busy' },
      { reason: 'summarize_circuit_open', level: 'warning', copy: 'chat.compact.skip.paused' },
      { reason: 'compression_anti_thrash_active', level: 'warning', copy: 'chat.compact.skip.ineffective' },
      { reason: 'timeout: summarizer exceeded 60s', level: 'error', copy: 'chat.compact.failed' },
    ] as const)(
      'words a compaction the server did not run for its reason: $reason',
      async ({ reason, level, copy }) => {
        mockRunManualCompaction.mockResolvedValue({ compacted: false, message_count: 2, tokens_saved: 0, reason });
        const { result } = renderCompact();

        await act(async () => {
          await result.current.executeCompact();
        });

        expect(toastMock[level]).toHaveBeenCalledWith(copy, { id: 'toast-1' });
        expect(toastMock.success).not.toHaveBeenCalled();
      },
    );

    it('reports a request that failed', async () => {
      mockRunManualCompaction.mockRejectedValue(new Error('network'));
      const { result } = renderCompact();

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(toastMock.error).toHaveBeenCalledWith('chat.compact.failed', { id: 'toast-1' });
    });
  });
});
