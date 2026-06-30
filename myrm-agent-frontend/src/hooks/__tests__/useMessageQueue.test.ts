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
});
