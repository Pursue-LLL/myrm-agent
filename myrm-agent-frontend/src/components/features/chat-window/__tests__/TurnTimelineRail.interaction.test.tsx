import { act, fireEvent, render, screen } from '@testing-library/react';
import { Profiler, type ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { TurnTimelineRail } from '../TurnTimelineRail';
import { jumpHandlers, LOADED_MESSAGES, OUTLINES, outline, userMessage } from './turnRailKit';

vi.mock('next-intl', async () => (await import('./turnRailKit')).nextIntlMock());
vi.mock('@/hooks/shared/useToast', async () => (await import('./turnRailKit')).toastHookMock());

type RailProps = ComponentProps<typeof TurnTimelineRail>;

function renderRail(props: Partial<RailProps> = {}) {
  const handlers = jumpHandlers();
  const element = (next: Partial<RailProps>) => (
    <>
      <TurnTimelineRail messages={LOADED_MESSAGES} turnOutlines={OUTLINES} {...handlers} {...props} {...next} />
      <button type="button">outside</button>
    </>
  );
  const view = render(element({}));
  return { ...handlers, unmount: view.unmount, update: (next: Partial<RailProps>) => view.rerender(element(next)) };
}

const rail = () => screen.getByTestId('turn-timeline-rail');
/** The layer inside the landmark that listens to the pointer and to focus leaving. */
const surface = () => rail().firstElementChild as HTMLElement;
const preview = () => screen.queryByTestId('turn-rail-preview');
const ticks = () => Array.from(rail().querySelectorAll<HTMLButtonElement>('[data-rail-tick]'));
const rect = (top: number, height = 0): DOMRect => ({
  top,
  height,
  bottom: top + height,
  left: 0,
  right: 0,
  width: 0,
  x: 0,
  y: top,
  toJSON: () => ({}),
});

/** jsdom has no layout: the rail starts at `barTop` and its twelve-pixel ticks run down from `firstTickTop`. */
function layOut(barTop: number, firstTickTop: number): void {
  rail().getBoundingClientRect = () => rect(barTop);
  ticks().forEach((button, index) => {
    button.getBoundingClientRect = () => rect(firstTickTop + index * 12, 12);
  });
}

const widths = () => ticks().map((button) => (button.firstElementChild as HTMLElement).style.width);
const pressAlt = (key: string) => fireEvent.keyDown(window, { key, altKey: true });
/** Lets a started load finish, so its follow-up state update happens inside act. */
const settle = () => act(async () => undefined);

beforeEach(() => {
  vi.resetAllMocks();
});

describe('TurnTimelineRail preview', () => {
  it('shows what a turn was about while its tick is hovered, and hides it when the pointer leaves', () => {
    renderRail();
    expect(preview()).toBeNull();

    fireEvent.mouseEnter(ticks()[0]);

    expect(preview()).toHaveTextContent('turn {"index":1}');
    expect(preview()).toHaveTextContent('loaded');
    expect(preview()).toHaveTextContent('userPrompt:Hello, help me refactor.');
    expect(preview()).toHaveTextContent('assistantReply:Sure, I will assist with refactoring.');

    fireEvent.mouseLeave(surface());

    expect(preview()).toBeNull();
  });

  it('tells apart turns in memory, older turns and the turn being generated', () => {
    renderRail({ messages: [...LOADED_MESSAGES, userMessage('u5', 'Newest question')] });
    const badge = () => preview()?.firstElementChild?.lastElementChild;

    fireEvent.mouseEnter(ticks()[0]);
    expect(badge()).toHaveClass('bg-primary/15');

    fireEvent.mouseEnter(ticks()[3]);
    expect(preview()).toHaveTextContent('unloaded');
    expect(badge()).toHaveClass('bg-muted');

    fireEvent.mouseEnter(ticks()[4]);
    expect(preview()).toHaveTextContent('inFlight');
    expect(badge()).toHaveClass('bg-amber-500/15');
    expect(preview()).toHaveTextContent('userPrompt:Newest question');
    expect(preview()).not.toHaveTextContent('assistantReply');
  });

  it('shows an ellipsis for a turn whose prompt is empty', () => {
    renderRail({ turnOutlines: [outline(1, 'u1', ''), ...OUTLINES.slice(1)] });

    fireEvent.mouseEnter(ticks()[0]);

    expect(preview()).toHaveTextContent('userPrompt:...');
  });

  it('hangs at the middle of the hovered tick, measured from the top of the rail', () => {
    renderRail();
    layOut(100, 130);

    fireEvent.mouseEnter(ticks()[1]);

    expect(preview()).toHaveStyle({ top: '48px' });
  });

  it('moves with its tick when the rail scrolls under a pointer that stays put', () => {
    renderRail();
    layOut(100, 130);
    fireEvent.mouseEnter(ticks()[1]);
    expect(preview()).toHaveStyle({ top: '48px' });

    layOut(100, 150);
    fireEvent.mouseEnter(ticks()[1]);

    expect(preview()).toHaveStyle({ top: '68px' });
  });

  it('follows the pointer to the tick that is vertically closest', () => {
    renderRail();
    layOut(100, 200);
    const previewedTurn = () => preview()?.textContent ?? '';

    fireEvent.mouseMove(surface(), { clientY: 229 });
    expect(previewedTurn()).toContain('turn {"index":3}');
    expect(preview()).toHaveStyle({ top: '130px' });

    fireEvent.mouseMove(surface(), { clientY: 1000 });
    expect(previewedTurn()).toContain('turn {"index":4}');

    fireEvent.mouseMove(surface(), { clientY: 0 });
    expect(previewedTurn()).toContain('turn {"index":1}');
  });

  it('widens the hovered tick and its neighbours, and the tick of the turn being read', () => {
    renderRail({ activeViewportTurn: 4 });
    expect(widths()).toEqual(['14px', '14px', '14px', '26px']);

    fireEvent.mouseEnter(ticks()[1]);

    expect(widths()).toEqual(['22px', '32px', '22px', '26px']);
  });

  it('widens an older turn less than one in memory', () => {
    renderRail();
    expect(widths()).toEqual(['14px', '14px', '14px', '8px']);

    fireEvent.mouseEnter(ticks()[3]);

    expect(widths()).toEqual(['14px', '16px', '22px', '24px']);
  });
});

describe('TurnTimelineRail ticks', () => {
  const marks = () => ticks().map((button) => button.firstElementChild as HTMLElement);

  it('draws turns in memory, older turns and the turn being generated differently', () => {
    renderRail({ messages: [...LOADED_MESSAGES, userMessage('u5', 'Newest question')] });

    expect(marks()[0]).toHaveClass('h-[5px]');
    expect(marks()[0]).not.toHaveClass('animate-pulse');
    expect(marks()[3]).toHaveClass('h-[3px]');
    expect(marks()[4]).toHaveClass('h-[5px]', 'animate-pulse');
  });

  it('rings the turn being read', () => {
    renderRail({ activeViewportTurn: 2 });

    expect(marks().map((mark) => mark.classList.contains('ring-2'))).toEqual([false, true, false, false]);
  });

  it('lights the hovered tick and the two on each side of it', () => {
    renderRail();
    const lit = () => marks().map((mark) => mark.classList.contains('bg-primary'));
    expect(lit()).toEqual([false, false, false, false]);

    fireEvent.mouseEnter(ticks()[0]);
    expect(lit()).toEqual([true, true, true, false]);

    fireEvent.mouseEnter(ticks()[3]);
    expect(lit()).toEqual([false, true, true, true]);
  });

  it('does not render again while the pointer stays on the same tick', () => {
    const commits = vi.fn();
    render(
      <Profiler id="rail" onRender={commits}>
        <TurnTimelineRail messages={LOADED_MESSAGES} turnOutlines={OUTLINES} {...jumpHandlers()} />
      </Profiler>,
    );
    layOut(0, 200);

    fireEvent.mouseMove(surface(), { clientY: 206 });
    // React may still spend one no-op pass on the first repeated update; later ones are skipped outright.
    fireEvent.mouseMove(surface(), { clientY: 207 });
    const settled = commits.mock.calls.length;

    fireEvent.mouseMove(surface(), { clientY: 205 });
    fireEvent.mouseMove(surface(), { clientY: 208 });
    expect(commits).toHaveBeenCalledTimes(settled);

    fireEvent.mouseMove(surface(), { clientY: 230 });
    expect(commits.mock.calls.length).toBeGreaterThan(settled);
  });
});

describe('TurnTimelineRail keyboard focus', () => {
  it('previews the focused tick and hides the preview when focus leaves the rail', () => {
    renderRail();

    act(() => ticks()[0].focus());
    expect(preview()).toHaveTextContent('turn {"index":1}');

    act(() => screen.getByRole('button', { name: 'outside' }).focus());

    expect(preview()).toBeNull();
  });

  it('hides the preview when focus leaves the page altogether', () => {
    renderRail();
    act(() => ticks()[0].focus());

    fireEvent.blur(ticks()[0], { relatedTarget: null });

    expect(preview()).toBeNull();
  });

  it('keeps the preview on screen while focus moves along the rail, now on the next tick', () => {
    renderRail();
    act(() => ticks()[0].focus());

    fireEvent.blur(ticks()[0], { relatedTarget: ticks()[1] });
    expect(preview()).toHaveTextContent('turn {"index":1}');

    act(() => ticks()[1].focus());
    expect(preview()).toHaveTextContent('turn {"index":2}');
  });

  it('starts without a preview again when the rail comes back after it was away', () => {
    const { update } = renderRail();
    fireEvent.mouseEnter(ticks()[1]);
    expect(preview()).not.toBeNull();

    update({ messages: LOADED_MESSAGES.slice(0, 3), turnOutlines: undefined });
    expect(screen.queryByTestId('turn-timeline-rail')).toBeNull();
    update({});

    expect(screen.getByTestId('turn-timeline-rail')).toBeInTheDocument();
    expect(preview()).toBeNull();
  });

  it('survives the rail shrinking under the pointer', () => {
    const { update } = renderRail();
    fireEvent.mouseEnter(ticks()[3]);
    expect(preview()).not.toBeNull();

    update({ turnOutlines: OUTLINES.slice(0, 3) });

    expect(screen.getByTestId('turn-timeline-rail')).toBeInTheDocument();
    expect(preview()).toBeNull();
  });
});

describe('TurnTimelineRail Alt+arrow keys', () => {
  it('moves to the turn before or after the one being read', () => {
    const { onJump } = renderRail({ activeViewportTurn: 2 });

    pressAlt('ArrowUp');
    pressAlt('ArrowDown');

    expect(onJump.mock.calls).toEqual([[0], [4]]);
  });

  it('stays on the first and the last turn at the ends', async () => {
    const { onJump, onLoadThroughTurn, update } = renderRail({ activeViewportTurn: 1 });
    onLoadThroughTurn.mockResolvedValue(true);

    pressAlt('ArrowUp');
    expect(onJump).toHaveBeenLastCalledWith(0);

    update({ activeViewportTurn: 4 });
    pressAlt('ArrowDown');
    await settle();

    expect(onLoadThroughTurn).toHaveBeenLastCalledWith('u4-unloaded');
  });

  it('starts from the last turn when nothing is being read', async () => {
    const { onJump, onLoadThroughTurn } = renderRail({ activeViewportTurn: null });
    onLoadThroughTurn.mockResolvedValue(true);

    pressAlt('ArrowUp');
    expect(onJump).toHaveBeenLastCalledWith(4);

    pressAlt('ArrowDown');
    await settle();

    expect(onLoadThroughTurn).toHaveBeenLastCalledWith('u4-unloaded');
  });

  it('starts from the ends when the turn being read is not on the rail', async () => {
    const { onJump, onLoadThroughTurn } = renderRail({ activeViewportTurn: 99 });
    onLoadThroughTurn.mockResolvedValue(true);

    pressAlt('ArrowDown');
    expect(onJump).toHaveBeenLastCalledWith(0);

    pressAlt('ArrowUp');
    await settle();

    expect(onLoadThroughTurn).toHaveBeenLastCalledWith('u4-unloaded');
  });

  it('loads an older turn it moves onto', async () => {
    const { onLoadThroughTurn } = renderRail({ activeViewportTurn: 3 });
    onLoadThroughTurn.mockResolvedValue(true);

    pressAlt('ArrowDown');
    await settle();

    expect(onLoadThroughTurn).toHaveBeenCalledWith('u4-unloaded');
  });

  it('keeps the default of the keys it does not use, and takes over the ones it uses', () => {
    renderRail({ activeViewportTurn: 2 });

    expect(fireEvent.keyDown(window, { key: 'ArrowUp' })).toBe(true);
    expect(fireEvent.keyDown(window, { key: 'ArrowLeft', altKey: true })).toBe(true);
    expect(fireEvent.keyDown(window, { key: 'ArrowUp', altKey: true })).toBe(false);
    expect(fireEvent.keyDown(window, { key: 'ArrowDown', altKey: true })).toBe(false);
  });

  it('is not listening while the rail is hidden or after it was removed', () => {
    const hidden = renderRail({ messages: LOADED_MESSAGES.slice(0, 3), turnOutlines: undefined });
    expect(pressAlt('ArrowUp')).toBe(true);
    hidden.unmount();
    const shown = renderRail({ activeViewportTurn: 2 });
    shown.unmount();

    expect(pressAlt('ArrowUp')).toBe(true);
    expect(hidden.onJump).not.toHaveBeenCalled();
    expect(shown.onJump).not.toHaveBeenCalled();
  });
});
