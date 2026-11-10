import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/store/chat/types';
import { deferred } from '@/test-utils/deferred';

import { TurnTimelineRail } from '../TurnTimelineRail';
import { jumpHandlers, kit, LOADED_MESSAGES, OUTLINES, userMessage } from './turnRailKit';

vi.mock('next-intl', async () => (await import('./turnRailKit')).nextIntlMock());
vi.mock('@/hooks/shared/useToast', async () => (await import('./turnRailKit')).toastHookMock());

function renderRail(props: Partial<ComponentProps<typeof TurnTimelineRail>> = {}) {
  const handlers = jumpHandlers();
  const view = render(<TurnTimelineRail messages={LOADED_MESSAGES} turnOutlines={OUTLINES} {...handlers} {...props} />);
  return { ...view, ...handlers };
}

const ticks = () => screen.queryAllByRole('button');
const tick = (turn: number) => screen.getByRole('button', { name: `jumpToTurn {"index":${turn}}` });
const isSpinning = (turn: number) => tick(turn).querySelector('.animate-spin') !== null;

beforeEach(() => {
  vi.resetAllMocks();
});

describe('TurnTimelineRail showing the turns', () => {
  it('renders nothing below three turns', () => {
    const { container } = renderRail({ messages: LOADED_MESSAGES.slice(0, 3), turnOutlines: OUTLINES.slice(0, 2) });

    expect(container).toBeEmptyDOMElement();
  });

  it('is a navigation landmark with one named tick per turn of the outline', () => {
    renderRail();

    expect(screen.getByRole('navigation', { name: 'ariaLabel' })).toBeInTheDocument();
    expect(ticks().map((button) => button.getAttribute('aria-label'))).toEqual([
      'jumpToTurn {"index":1}',
      'jumpToTurn {"index":2}',
      'jumpToTurn {"index":3}',
      'jumpToTurn {"index":4}',
    ]);
  });

  it('builds the turns from the loaded messages when there is no outline', () => {
    renderRail({ turnOutlines: undefined });

    expect(ticks()).toHaveLength(3);
  });

  it('adds a tick for a message the outline does not know yet, such as the turn being generated', () => {
    const { onJump } = renderRail({ messages: [...LOADED_MESSAGES, userMessage('u5', 'Newest question')] });

    expect(ticks()).toHaveLength(5);
    fireEvent.click(tick(5));

    expect(onJump).toHaveBeenCalledWith(5);
  });

  it('leaves out the notices the system writes after background work', () => {
    const notice: Message = { ...userMessage('n1', 'Task finished'), wakeupNotice: 'followup' };

    renderRail({ messages: [...LOADED_MESSAGES, notice], turnOutlines: undefined });

    expect(ticks()).toHaveLength(3);
  });

  it('marks the turn being read', () => {
    renderRail({ activeViewportTurn: 2 });

    expect(ticks().map((button) => button.getAttribute('aria-current'))).toEqual([null, 'location', null, null]);
  });

  it('dims while a reply is streaming and makes room for the goal panel', () => {
    const { rerender, onJump } = renderRail();
    const rail = () => screen.getByTestId('turn-timeline-rail');
    expect(rail()).toHaveClass('opacity-100', 'right-3');
    expect(rail()).not.toHaveClass('opacity-60', 'xl:right-[340px]');

    rerender(
      <TurnTimelineRail messages={LOADED_MESSAGES} turnOutlines={OUTLINES} onJump={onJump} loading hasGoalPanel />,
    );

    expect(rail()).toHaveClass('opacity-60', 'xl:right-[340px]');
    expect(rail()).not.toHaveClass('opacity-100');
  });
});

describe('TurnTimelineRail jumping', () => {
  it('scrolls straight to a turn that is in memory', () => {
    const { onJump, onJumpToMessageId, onLoadThroughTurn } = renderRail();

    fireEvent.click(tick(1));
    fireEvent.click(tick(3));

    expect(onJump.mock.calls).toEqual([[0], [4]]);
    expect(onJumpToMessageId).not.toHaveBeenCalled();
    expect(onLoadThroughTurn).not.toHaveBeenCalled();
  });

  it('loads an older turn first, shows progress on its tick, and jumps to it once it arrived', async () => {
    const load = deferred<boolean>();
    const { onJump, onJumpToMessageId, onLoadThroughTurn } = renderRail();
    onLoadThroughTurn.mockReturnValue(load.promise);

    fireEvent.click(tick(4));

    expect(onLoadThroughTurn).toHaveBeenCalledWith('u4-unloaded');
    expect([1, 2, 3, 4].map(isSpinning)).toEqual([false, false, false, true]);
    expect(onJumpToMessageId).not.toHaveBeenCalled();

    load.resolve(true);

    await vi.waitFor(() => expect(onJumpToMessageId).toHaveBeenCalledWith('u4-unloaded'));
    expect(isSpinning(4)).toBe(false);
    expect(onJump).not.toHaveBeenCalled();
    expect(kit.toast).not.toHaveBeenCalled();
  });

  it('ignores every click while a turn is loading', async () => {
    const load = deferred<boolean>();
    const { onJump, onLoadThroughTurn } = renderRail();
    onLoadThroughTurn.mockReturnValue(load.promise);

    fireEvent.click(tick(4));
    fireEvent.click(tick(4));
    fireEvent.click(tick(1));

    expect(onLoadThroughTurn).toHaveBeenCalledTimes(1);
    expect(onJump).not.toHaveBeenCalled();

    load.resolve(true);
    await vi.waitFor(() => expect(isSpinning(4)).toBe(false));
    fireEvent.click(tick(1));

    expect(onJump).toHaveBeenCalledWith(0);
  });

  it('stays where it is and says so when the turn could not be reached', async () => {
    const { onJump, onJumpToMessageId, onLoadThroughTurn } = renderRail();
    onLoadThroughTurn.mockResolvedValue(false);

    fireEvent.click(tick(4));

    await vi.waitFor(() => expect(kit.toast).toHaveBeenCalledWith({ title: 'loadFailed', variant: 'destructive' }));
    expect(isSpinning(4)).toBe(false);
    expect(onJumpToMessageId).not.toHaveBeenCalled();
    expect(onJump).not.toHaveBeenCalled();

    onLoadThroughTurn.mockResolvedValue(true);
    fireEvent.click(tick(4));

    await vi.waitFor(() => expect(onJumpToMessageId).toHaveBeenCalledWith('u4-unloaded'));
  });

  it('reports a failing load and can be used again', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { onJumpToMessageId, onLoadThroughTurn } = renderRail();
    onLoadThroughTurn.mockRejectedValue(new Error('offline'));

    fireEvent.click(tick(4));

    await vi.waitFor(() => expect(kit.toast).toHaveBeenCalledTimes(1));
    expect(error).toHaveBeenCalledWith('Failed to load through target turn:', expect.any(Error));
    expect(isSpinning(4)).toBe(false);
    expect(onJumpToMessageId).not.toHaveBeenCalled();
  });

  it('does nothing for an older turn when it was given no way to load it', () => {
    renderRail({ onLoadThroughTurn: undefined });

    fireEvent.click(tick(4));

    expect(isSpinning(4)).toBe(false);
    expect(kit.toast).not.toHaveBeenCalled();
  });

  it('finishes loading even when it was given no way to jump by id', async () => {
    const { onLoadThroughTurn } = renderRail({ onJumpToMessageId: undefined });
    onLoadThroughTurn.mockResolvedValue(true);

    fireEvent.click(tick(4));

    await vi.waitFor(() => expect(onLoadThroughTurn).toHaveBeenCalledTimes(1));
    await vi.waitFor(() => expect(isSpinning(4)).toBe(false));
    expect(kit.toast).not.toHaveBeenCalled();
  });
});
