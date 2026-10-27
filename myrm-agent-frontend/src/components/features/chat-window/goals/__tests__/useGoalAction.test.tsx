// @vitest-environment jsdom
/**
 * One goal control is out at a time, whichever button of the card sent it.
 *
 * Real scenario: "retry now" in the usage-limit row and the resume button of the header both put a waiting goal back
 * to work; pressing both before the server answered must not send the request twice.
 */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { postMock, sonnerToast, stableT } = vi.hoisted(() => ({
  stableT: (key: string) => key,
  postMock: vi.fn(),
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/store/chat/goals/goalActionClient', () => ({ postGoalAction: postMock }));

import { useGoalAction } from '../useGoalAction';

describe('useGoalAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('ignores a second control while the first is out, and takes the next one once it was answered', async () => {
    let answer: (outcome: 'done') => void = () => undefined;
    postMock.mockReturnValueOnce(new Promise((resolve) => (answer = resolve))).mockResolvedValue('done');
    const { result } = renderHook(() => useGoalAction('chat-1'));

    let first: Promise<boolean> = Promise.resolve(false);
    let second = true;
    await act(async () => {
      first = result.current.run('unwait');
      second = await result.current.run('resume');
    });

    expect(second).toBe(false);
    expect(result.current.pendingAction).toBe('unwait');
    expect(postMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      answer('done');
      expect(await first).toBe(true);
    });

    expect(result.current.pendingAction).toBeNull();
    await act(async () => {
      expect(await result.current.run('cancel')).toBe(true);
    });
    expect(postMock.mock.calls.map(([, action]) => action)).toEqual(['unwait', 'cancel']);
  });

  it('keeps a control that is still out from holding the controls of another chat', async () => {
    let answer: (outcome: 'done') => void = () => undefined;
    postMock.mockReturnValueOnce(new Promise((resolve) => (answer = resolve))).mockResolvedValue('done');
    const { result, rerender } = renderHook(({ chatId }) => useGoalAction(chatId), {
      initialProps: { chatId: 'chat-1' },
    });

    let first: Promise<boolean> = Promise.resolve(false);
    await act(async () => {
      first = result.current.run('resume');
    });
    expect(result.current.pendingAction).toBe('resume');

    rerender({ chatId: 'chat-2' });
    expect(result.current.pendingAction).toBeNull();
    await act(async () => {
      expect(await result.current.run('pause')).toBe(true);
    });

    rerender({ chatId: 'chat-1' });
    expect(result.current.pendingAction).toBe('resume');
    await act(async () => {
      expect(await result.current.run('resume')).toBe(false);
    });
    expect(postMock.mock.calls.map(([chatId, action]) => [chatId, action])).toEqual([
      ['chat-1', 'resume'],
      ['chat-2', 'pause'],
    ]);

    await act(async () => {
      answer('done');
      await first;
    });
    expect(result.current.pendingAction).toBeNull();
  });

  it('sends nothing without a chat', async () => {
    const { result } = renderHook(() => useGoalAction(null));

    await act(async () => {
      expect(await result.current.run('pause')).toBe(false);
    });

    expect(postMock).not.toHaveBeenCalled();
  });

  it('frees the controls when the request ends in a failure', async () => {
    postMock.mockResolvedValueOnce('failed').mockResolvedValue('done');
    const { result } = renderHook(() => useGoalAction('chat-1'));

    await act(async () => {
      expect(await result.current.run('resume')).toBe(false);
    });
    expect(sonnerToast.error).toHaveBeenCalledWith('goalActionFailed_resume');

    await act(async () => {
      expect(await result.current.run('resume')).toBe(true);
    });
  });
});
