import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCompactChat } from '@/hooks/message-input/useCompactChat';

const mockCompactChat = vi.hoisted(() => vi.fn());
const toastMock = vi.hoisted(() => ({
  loading: vi.fn(() => 'toast-1'),
  success: vi.fn(),
  info: vi.fn(),
  warning: vi.fn(),
  error: vi.fn(),
}));

vi.mock('@/services/contextCompaction', () => ({ compactChat: mockCompactChat }));
vi.mock('@/lib/utils/toast', () => ({ toast: toastMock }));

const loadMessages = vi.fn(async () => undefined);

function renderCompact() {
  return renderHook(() => useCompactChat('chat-1', loadMessages));
}

describe('useCompactChat', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockCompactChat.mockResolvedValue({ compacted: true, message_count: 8, tokens_saved: 1200, reason: null });
  });

  describe('asking before it compacts', () => {
    it('compacts at once when the reminder was switched off', async () => {
      localStorage.setItem('dontRemindCompact', 'true');
      const { result } = renderCompact();

      await act(async () => {
        await result.current.requestCompact('billing');
      });

      expect(mockCompactChat).toHaveBeenCalledWith('chat-1', 'billing');
      expect(result.current.showCompactConfirm).toBe(false);
    });

    it('opens the confirmation instead of compacting, then compacts with the topic it was asked for', async () => {
      const { result } = renderCompact();

      await act(async () => {
        await result.current.requestCompact('billing');
      });

      expect(result.current.showCompactConfirm).toBe(true);
      expect(mockCompactChat).not.toHaveBeenCalled();

      await act(async () => {
        result.current.confirmCompact();
      });

      expect(mockCompactChat).toHaveBeenCalledTimes(1);
      expect(mockCompactChat).toHaveBeenCalledWith('chat-1', 'billing');
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

      expect(mockCompactChat).toHaveBeenLastCalledWith('chat-1', undefined);
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
      const { result } = renderHook(() => useCompactChat(undefined, loadMessages));

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(toastMock.warning).toHaveBeenCalledWith('compact.noChatId');
      expect(mockCompactChat).not.toHaveBeenCalled();
    });

    it('reloads the transcript and names the topic the server kept', async () => {
      mockCompactChat.mockResolvedValue({
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

      expect(toastMock.success).toHaveBeenCalledWith('compact.success (billing)', { id: 'toast-1' });
      expect(loadMessages).toHaveBeenCalledWith('chat-1');
    });

    it('says why nothing was compacted and leaves the transcript alone', async () => {
      mockCompactChat.mockResolvedValue({ compacted: false, message_count: 2, tokens_saved: 0, reason: 'too short' });
      const { result } = renderCompact();

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(toastMock.info).toHaveBeenCalledWith('compact.skipped', { id: 'toast-1' });
      expect(loadMessages).not.toHaveBeenCalled();
    });

    it('reports a request that failed', async () => {
      mockCompactChat.mockRejectedValue(new Error('network'));
      const { result } = renderCompact();

      await act(async () => {
        await result.current.executeCompact();
      });

      expect(toastMock.error).toHaveBeenCalledWith('compact.failed', { id: 'toast-1' });
      expect(loadMessages).not.toHaveBeenCalled();
    });
  });
});
