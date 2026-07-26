import { act, renderHook } from '@testing-library/react';

import { useMessageQueue } from '../useMessageQueue';

describe('useMessageQueue', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
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

  it('editMessage updates text of a specific queued message', () => {
    const { result } = renderHook(() => useMessageQueue('chat-edit'));

    act(() => {
      result.current.enqueue('original text', []);
      result.current.enqueue('second message', []);
    });

    expect(result.current.queue).toHaveLength(2);
    const targetId = result.current.queue[0]!.id;

    act(() => {
      result.current.editMessage(targetId, 'updated text');
    });

    expect(result.current.queue[0]!.text).toBe('updated text');
    expect(result.current.queue[1]!.text).toBe('second message');
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
    expect(result.current.queue[0]!.text).toBe('hello');
  });

  it('requeue inserts message at head preserving original id', () => {
    const { result } = renderHook(() => useMessageQueue('chat-requeue'));

    act(() => {
      result.current.enqueue('first', []);
      result.current.enqueue('second', []);
    });

    expect(result.current.queue).toHaveLength(2);
    const firstMsg = result.current.queue[0]!;

    act(() => {
      result.current.dequeue();
    });

    expect(result.current.queue).toHaveLength(1);
    expect(result.current.queue[0]!.text).toBe('second');

    act(() => {
      result.current.requeue(firstMsg);
    });

    expect(result.current.queue).toHaveLength(2);
    expect(result.current.queue[0]!.id).toBe(firstMsg.id);
    expect(result.current.queue[0]!.text).toBe('first');
    expect(result.current.queue[1]!.text).toBe('second');
  });

  it('requeue deduplicates if message already in queue', () => {
    const { result } = renderHook(() => useMessageQueue('chat-requeue-dedup'));

    act(() => {
      result.current.enqueue('msg', []);
    });

    const msg = result.current.queue[0]!;

    act(() => {
      result.current.requeue(msg);
    });

    expect(result.current.queue).toHaveLength(1);
    expect(result.current.queue[0]!.id).toBe(msg.id);
  });

  it('dequeue returns null on empty queue', () => {
    const { result } = renderHook(() => useMessageQueue('chat-empty'));

    let dequeued: ReturnType<typeof result.current.dequeue>;
    act(() => {
      dequeued = result.current.dequeue();
    });

    expect(dequeued!).toBeNull();
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
});
