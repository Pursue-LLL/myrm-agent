import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useMessageQueueStore } from '@/store/chat/useMessageQueueStore';
import { useMessageQueue } from '../useMessageQueue';

const chatStoreRef = vi.hoisted(() => ({ incognitoMode: false }));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { incognitoMode: boolean }) => unknown) => selector(chatStoreRef),
}));

const QUEUE_KEY = (chatId: string) => `myrm_message_queue_${chatId}`;
const PAUSE_KEY = (chatId: string) => `myrm_message_queue_paused_${chatId}`;

/** Simulates a page reload: in-memory queue state is gone, localStorage survives. */
function simulateReload(): void {
  useMessageQueueStore.setState({ queues: {} });
}

describe('useMessageQueue', () => {
  beforeEach(() => {
    localStorage.clear();
    chatStoreRef.incognitoMode = false;
    useMessageQueueStore.setState({ queues: {} });
  });

  it('preserves typed archive restore actions in queued messages', () => {
    const { result } = renderHook(() => useMessageQueue('chat-restore'));
    const archiveRestoreActions = [
      {
        type: 'archive_restore' as const,
        restoreArg: '.context/chat-restore/compacted/result.txt:10-20',
      },
    ];

    act(() => {
      result.current.enqueue('restore archived range', [], archiveRestoreActions);
    });

    expect(result.current.queue).toHaveLength(1);
    expect(result.current.queue[0]?.archiveRestoreActions).toEqual(archiveRestoreActions);
  });

  it('returns the 1-based position of the queued message', () => {
    const { result } = renderHook(() => useMessageQueue('chat-position'));

    let first = 0;
    let second = 0;
    act(() => {
      first = result.current.enqueue('first', []);
      second = result.current.enqueue('second', []);
    });

    expect([first, second]).toEqual([1, 2]);
  });

  it('shares one queue between every consumer of the same chat', () => {
    const composer = renderHook(() => useMessageQueue('chat-shared'));
    const selectionAction = renderHook(() => useMessageQueue('chat-shared'));

    act(() => {
      selectionAction.result.current.enqueue('from the artifact toolbar', []);
    });

    expect(composer.result.current.queue.map((message) => message.text)).toEqual(['from the artifact toolbar']);
  });

  it('keeps chats isolated from each other', () => {
    const { result, rerender } = renderHook(({ chatId }) => useMessageQueue(chatId), {
      initialProps: { chatId: 'chat-a' },
    });

    act(() => {
      result.current.enqueue('only in A', []);
    });
    rerender({ chatId: 'chat-b' });

    expect(result.current.queue).toHaveLength(0);

    rerender({ chatId: 'chat-a' });
    expect(result.current.queue.map((message) => message.text)).toEqual(['only in A']);
  });

  it('is inert without an active chat', () => {
    const { result } = renderHook(() => useMessageQueue(null));

    let position = -1;
    act(() => {
      position = result.current.enqueue('nowhere', []);
    });

    expect(position).toBe(0);
    expect(result.current.queue).toHaveLength(0);
    expect(useMessageQueueStore.getState().queues).toEqual({});
  });

  it('editMessage updates text of a specific queued message', () => {
    const { result } = renderHook(() => useMessageQueue('chat-edit'));

    act(() => {
      result.current.enqueue('original text', []);
      result.current.enqueue('second message', []);
    });

    expect(result.current.queue).toHaveLength(2);
    const targetId = result.current.queue[0].id;

    act(() => {
      result.current.editMessage(targetId, 'updated text');
    });

    expect(result.current.queue[0].text).toBe('updated text');
    expect(result.current.queue[1].text).toBe('second message');
  });

  it('editMessage is a no-op for non-existent id', () => {
    const { result } = renderHook(() => useMessageQueue('chat-edit-noop'));

    act(() => {
      result.current.enqueue('hello', []);
    });

    act(() => {
      result.current.editMessage('non-existent-id', 'new text');
    });

    expect(result.current.queue).toHaveLength(1);
    expect(result.current.queue[0].text).toBe('hello');
  });

  it('exposes the message under edit and releases it when the message is removed', () => {
    const { result } = renderHook(() => useMessageQueue('chat-editing'));

    act(() => {
      result.current.enqueue('draft', []);
    });
    const id = result.current.queue[0].id;

    act(() => {
      result.current.setEditingId(id);
    });
    expect(result.current.editingId).toBe(id);

    act(() => {
      result.current.removeMessage(id);
    });
    expect(result.current.editingId).toBeNull();
    expect(result.current.queue).toHaveLength(0);
  });

  it('clearQueue removes all messages', () => {
    const { result } = renderHook(() => useMessageQueue('chat-clear'));

    act(() => {
      result.current.enqueue('a', []);
      result.current.enqueue('b', []);
      result.current.enqueue('c', []);
    });

    expect(result.current.queue).toHaveLength(3);

    act(() => {
      result.current.clearQueue();
    });

    expect(result.current.queue).toHaveLength(0);
  });

  describe('reorder', () => {
    it('moves item from one position to another', () => {
      const { result } = renderHook(() => useMessageQueue('chat-reorder'));

      act(() => {
        result.current.enqueue('A', []);
        result.current.enqueue('B', []);
        result.current.enqueue('C', []);
      });

      act(() => {
        result.current.reorder(2, 0);
      });

      expect(result.current.queue.map((m) => m.text)).toEqual(['C', 'A', 'B']);
    });

    it('is a no-op when oldIndex equals newIndex', () => {
      const { result } = renderHook(() => useMessageQueue('chat-reorder-same'));

      act(() => {
        result.current.enqueue('A', []);
        result.current.enqueue('B', []);
      });

      const before = result.current.queue;

      act(() => {
        result.current.reorder(0, 0);
      });

      expect(result.current.queue).toBe(before);
    });

    it('is a no-op for out-of-bounds indices', () => {
      const { result } = renderHook(() => useMessageQueue('chat-reorder-oob'));

      act(() => {
        result.current.enqueue('A', []);
        result.current.enqueue('B', []);
      });

      const before = result.current.queue;

      act(() => {
        result.current.reorder(-1, 0);
      });

      expect(result.current.queue).toBe(before);

      act(() => {
        result.current.reorder(0, 5);
      });

      expect(result.current.queue).toBe(before);
    });
  });

  describe('persistence', () => {
    it('writes the queue to localStorage and restores it after a reload', () => {
      const first = renderHook(() => useMessageQueue('chat-persist'));
      act(() => {
        first.result.current.enqueue('survives reload', []);
      });
      expect(JSON.parse(localStorage.getItem(QUEUE_KEY('chat-persist')) ?? '[]')).toHaveLength(1);
      first.unmount();

      simulateReload();
      const second = renderHook(() => useMessageQueue('chat-persist'));

      expect(second.result.current.queue.map((message) => message.text)).toEqual(['survives reload']);
    });

    it('does not overwrite the stored queue with an empty one before it was restored', () => {
      localStorage.setItem(
        QUEUE_KEY('chat-hydrate-first'),
        JSON.stringify([{ id: 'stored-1', text: 'stored', files: [], timestamp: 1 }]),
      );

      renderHook(() => useMessageQueue('chat-hydrate-first'));

      expect(JSON.parse(localStorage.getItem(QUEUE_KEY('chat-hydrate-first')) ?? '[]')).toHaveLength(1);
    });

    it('persists the pause marker so a stopped queue stays paused after a reload', () => {
      const first = renderHook(() => useMessageQueue('chat-paused'));
      act(() => {
        first.result.current.enqueue('held back', []);
      });
      act(() => {
        useMessageQueueStore.getState().pauseOnStop('chat-paused');
      });
      expect(localStorage.getItem(PAUSE_KEY('chat-paused'))).toBe('stopped');
      first.unmount();

      simulateReload();
      const second = renderHook(() => useMessageQueue('chat-paused'));
      expect(second.result.current.pausedReason).toBe('stopped');

      act(() => {
        second.result.current.resume();
      });
      expect(second.result.current.pausedReason).toBeNull();
      expect(localStorage.getItem(PAUSE_KEY('chat-paused'))).toBeNull();
    });

    it('removes the stored entries once the queue is empty', () => {
      const { result } = renderHook(() => useMessageQueue('chat-empty-storage'));
      act(() => {
        result.current.enqueue('short lived', []);
      });
      const id = result.current.queue[0].id;

      act(() => {
        result.current.removeMessage(id);
      });

      expect(localStorage.getItem(QUEUE_KEY('chat-empty-storage'))).toBeNull();
    });

    it('keeps incognito queues in memory only', () => {
      chatStoreRef.incognitoMode = true;
      const { result } = renderHook(() => useMessageQueue('chat-incognito'));

      act(() => {
        result.current.enqueue('private follow-up', []);
      });

      expect(result.current.queue).toHaveLength(1);
      expect(localStorage.getItem(QUEUE_KEY('chat-incognito'))).toBeNull();
    });
  });
});
