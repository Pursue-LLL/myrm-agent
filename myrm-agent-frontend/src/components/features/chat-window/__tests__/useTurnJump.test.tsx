import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import type { RailTurnItem } from '../turnRailModel';
import { useTurnJump } from '../useTurnJump';
import { jumpHandlers, kit } from './turnRailKit';

vi.mock('next-intl', async () => (await import('./turnRailKit')).nextIntlMock());
vi.mock('@/hooks/shared/useToast', async () => (await import('./turnRailKit')).toastHookMock());

const turn = (turnIndex: number, overrides: Partial<RailTurnItem> = {}): RailTurnItem => ({
  turnIndex,
  userMessageId: `u${turnIndex}`,
  assistantMessageId: null,
  promptPreview: '',
  replyPreview: null,
  isLoaded: true,
  messageIndex: turnIndex * 2,
  ...overrides,
});
const inMemory = turn(2);
const older = turn(1, { isLoaded: false, messageIndex: -1 });

function setup() {
  const handlers = jumpHandlers();
  const hook = renderHook(() => useTurnJump(handlers));
  const jump = (item: RailTurnItem) => act(() => hook.result.current.jumpToTurn(item));
  return { ...handlers, hook, jump };
}

beforeEach(() => {
  vi.resetAllMocks();
});

describe('useTurnJump', () => {
  it('scrolls to a turn in memory by its message index and reports success', async () => {
    const { onJump, onJumpToMessageId, onLoadThroughTurn, jump } = setup();

    await expect(jump(inMemory)).resolves.toBe(true);

    expect(onJump).toHaveBeenCalledWith(4);
    expect(onJumpToMessageId).not.toHaveBeenCalled();
    expect(onLoadThroughTurn).not.toHaveBeenCalled();
  });

  it('loads an older turn, announces which one is loading, then jumps to it by id', async () => {
    const load = deferred<boolean>();
    const { onJump, onJumpToMessageId, onLoadThroughTurn, hook } = setup();
    onLoadThroughTurn.mockReturnValue(load.promise);
    expect(hook.result.current.loadingTurnIndex).toBeNull();

    let outcome!: Promise<boolean>;
    act(() => {
      outcome = hook.result.current.jumpToTurn(older);
    });

    expect(hook.result.current.loadingTurnIndex).toBe(1);
    expect(onLoadThroughTurn).toHaveBeenCalledWith('u1');
    expect(onJumpToMessageId).not.toHaveBeenCalled();

    await act(async () => {
      load.resolve(true);
      await expect(outcome).resolves.toBe(true);
    });

    expect(hook.result.current.loadingTurnIndex).toBeNull();
    expect(onJumpToMessageId).toHaveBeenCalledWith('u1');
    expect(onJump).not.toHaveBeenCalled();
    expect(kit.toast).not.toHaveBeenCalled();
  });

  it('reports success without a jump by id when there is no handler for it', async () => {
    const { onLoadThroughTurn, hook } = setup();
    const withoutIdJump = renderHook(() => useTurnJump({ onJump: vi.fn(), onLoadThroughTurn }));
    onLoadThroughTurn.mockResolvedValue(true);

    await expect(act(() => withoutIdJump.result.current.jumpToTurn(older))).resolves.toBe(true);

    expect(hook.result.current.loadingTurnIndex).toBeNull();
    expect(withoutIdJump.result.current.loadingTurnIndex).toBeNull();
  });

  it('does not move and tells the user when the turn did not arrive', async () => {
    const { onJump, onJumpToMessageId, onLoadThroughTurn, hook, jump } = setup();
    onLoadThroughTurn.mockResolvedValue(false);

    await expect(jump(older)).resolves.toBe(false);

    expect(onJumpToMessageId).not.toHaveBeenCalled();
    expect(onJump).not.toHaveBeenCalled();
    expect(kit.toast).toHaveBeenCalledWith({ title: 'loadFailed', variant: 'destructive' });
    expect(hook.result.current.loadingTurnIndex).toBeNull();
  });

  it('logs and reports a load that failed, and can load again afterwards', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { onJumpToMessageId, onLoadThroughTurn, jump } = setup();
    onLoadThroughTurn.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(true);

    await expect(jump(older)).resolves.toBe(false);

    expect(error).toHaveBeenCalledWith('Failed to load through target turn:', expect.any(Error));
    expect(kit.toast).toHaveBeenCalledTimes(1);

    await expect(jump(older)).resolves.toBe(true);

    expect(onJumpToMessageId).toHaveBeenCalledWith('u1');
    expect(kit.toast).toHaveBeenCalledTimes(1);
  });

  it('refuses any jump while a turn is loading, without telling the user', async () => {
    const load = deferred<boolean>();
    const { onJump, onLoadThroughTurn, hook, jump } = setup();
    onLoadThroughTurn.mockReturnValue(load.promise);
    act(() => void hook.result.current.jumpToTurn(older));

    await expect(jump(older)).resolves.toBe(false);
    await expect(jump(inMemory)).resolves.toBe(false);

    expect(onLoadThroughTurn).toHaveBeenCalledTimes(1);
    expect(onJump).not.toHaveBeenCalled();
    expect(kit.toast).not.toHaveBeenCalled();

    await act(async () => load.resolve(true));
  });

  it('cannot reach an older turn without a way to load it, and does not complain', async () => {
    const { hook } = setup();
    const withoutLoader = renderHook(() => useTurnJump({ onJump: vi.fn() }));

    await expect(act(() => withoutLoader.result.current.jumpToTurn(older))).resolves.toBe(false);

    expect(kit.toast).not.toHaveBeenCalled();
    expect(withoutLoader.result.current.loadingTurnIndex).toBeNull();
    expect(hook.result.current.loadingTurnIndex).toBeNull();
  });
});
