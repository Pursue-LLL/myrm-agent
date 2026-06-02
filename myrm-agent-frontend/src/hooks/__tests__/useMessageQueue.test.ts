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
});
