import { beforeEach, describe, expect, it } from 'vitest';
import { useRewindStore } from '../useRewindStore';

describe('useRewindStore', () => {
  beforeEach(() => {
    useRewindStore.getState().closeRewind();
  });

  it('initializes with null target', () => {
    expect(useRewindStore.getState().target).toBeNull();
  });

  it('sets and clears rewind target', () => {
    useRewindStore.getState().openRewind({
      chatId: 'c1',
      messageId: 'm1',
      messageIndex: 2,
    });

    expect(useRewindStore.getState().target).toEqual({
      chatId: 'c1',
      messageId: 'm1',
      messageIndex: 2,
    });

    useRewindStore.getState().closeRewind();
    expect(useRewindStore.getState().target).toBeNull();
  });
});
