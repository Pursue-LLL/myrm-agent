import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import { MobileTurnOutlineSheet } from '../MobileTurnOutlineSheet';
import { jumpHandlers, kit, LOADED_MESSAGES, OUTLINES, outline, userMessage } from './turnRailKit';

vi.mock('next-intl', async () => (await import('./turnRailKit')).nextIntlMock());
vi.mock('@/hooks/shared/useToast', async () => (await import('./turnRailKit')).toastHookMock());

type SheetProps = ComponentProps<typeof MobileTurnOutlineSheet>;

function renderSheet(props: Partial<SheetProps> = {}) {
  const handlers = jumpHandlers();
  const element = (next: Partial<SheetProps>) => (
    <MobileTurnOutlineSheet
      messages={LOADED_MESSAGES}
      turnOutlines={OUTLINES}
      trigger={<button type="button">open outline</button>}
      {...handlers}
      {...props}
      {...next}
    />
  );
  const view = render(element({}));
  return { ...handlers, update: (next: Partial<SheetProps>) => view.rerender(element(next)) };
}

const openSheet = () => fireEvent.click(screen.getByRole('button', { name: 'open outline' }));
const sheet = () => screen.queryByRole('dialog');
const row = (turn: number) => screen.getByRole('button', { name: new RegExp(`^turn \\{"index":${turn}\\}`) });
const badge = (turn: number) => row(turn).firstElementChild?.lastElementChild;
const rowLabel = (turn: number) => badge(turn)?.textContent;

beforeEach(() => {
  vi.resetAllMocks();
});

describe('MobileTurnOutlineSheet listing', () => {
  it('shows neither the trigger nor a sheet below three turns', () => {
    renderSheet({ messages: LOADED_MESSAGES.slice(0, 3), turnOutlines: undefined });

    expect(screen.queryByRole('button', { name: 'open outline' })).toBeNull();
    expect(sheet()).toBeNull();
  });

  it('stays closed until its trigger is used', () => {
    renderSheet();

    expect(screen.getByRole('button', { name: 'open outline' })).toBeInTheDocument();
    expect(sheet()).toBeNull();
  });

  it('closes when it is dismissed', async () => {
    renderSheet();
    openSheet();
    expect(sheet()).not.toBeNull();

    fireEvent.keyDown(sheet() as HTMLElement, { key: 'Escape' });

    await vi.waitFor(() => expect(sheet()).toBeNull());
  });

  it('lists every turn with its state and what it was about', () => {
    renderSheet({ messages: [...LOADED_MESSAGES, userMessage('u5', 'Newest question')] });

    openSheet();

    expect(within(sheet() as HTMLElement).getByText('title')).toBeInTheDocument();
    expect(screen.getAllByRole('button').filter((button) => button.textContent?.includes('turn {'))).toHaveLength(5);
    expect(row(1)).toHaveTextContent('Hello, help me refactor.');
    expect(row(1)).toHaveTextContent('Sure, I will assist with refactoring.');
    expect([1, 2, 3, 4, 5].map(rowLabel)).toEqual(['loaded', 'loaded', 'loaded', 'unloaded', 'inFlight']);
    expect(badge(1)).toHaveClass('bg-primary/10');
    expect(badge(4)).toHaveClass('bg-muted');
    expect(badge(5)).toHaveClass('bg-amber-500/10');
    expect(row(5)).toHaveTextContent('Newest question');
  });

  it('shows an ellipsis for a turn whose prompt is empty and no reply line when there is none', () => {
    renderSheet({ turnOutlines: [{ ...OUTLINES[2], prompt_preview: '' }, OUTLINES[0], OUTLINES[1]] });

    openSheet();

    expect(row(3)).toHaveTextContent('...');
    expect(row(3).querySelectorAll('p')).toHaveLength(1);
  });
});

describe('MobileTurnOutlineSheet choosing a turn', () => {
  it('scrolls to a turn that is in memory and closes', async () => {
    const { onJump, onLoadThroughTurn } = renderSheet();
    openSheet();

    fireEvent.click(row(2));

    await vi.waitFor(() => expect(sheet()).toBeNull());
    expect(onJump).toHaveBeenCalledWith(2);
    expect(onLoadThroughTurn).not.toHaveBeenCalled();
  });

  it('shows the turn as loading, jumps to it by id once it arrived and then closes', async () => {
    const load = deferred<boolean>();
    const { onJumpToMessageId, onLoadThroughTurn } = renderSheet();
    onLoadThroughTurn.mockReturnValue(load.promise);
    openSheet();

    fireEvent.click(row(4));

    expect(onLoadThroughTurn).toHaveBeenCalledWith('u4-unloaded');
    expect(rowLabel(4)).toBe('loading');
    expect([1, 2, 3].map(rowLabel)).toEqual(['loaded', 'loaded', 'loaded']);
    expect(sheet()).not.toBeNull();
    expect(onJumpToMessageId).not.toHaveBeenCalled();

    load.resolve(true);

    await vi.waitFor(() => expect(sheet()).toBeNull());
    expect(onJumpToMessageId).toHaveBeenCalledWith('u4-unloaded');
  });

  it('stays open and says so when the turn could not be reached, so another try is possible', async () => {
    const { onJump, onJumpToMessageId, onLoadThroughTurn } = renderSheet();
    onLoadThroughTurn.mockResolvedValue(false);
    openSheet();

    fireEvent.click(row(4));

    await vi.waitFor(() => expect(kit.toast).toHaveBeenCalledWith({ title: 'loadFailed', variant: 'destructive' }));
    expect(sheet()).not.toBeNull();
    expect(rowLabel(4)).toBe('unloaded');
    expect(onJumpToMessageId).not.toHaveBeenCalled();
    expect(onJump).not.toHaveBeenCalled();

    onLoadThroughTurn.mockResolvedValue(true);
    fireEvent.click(row(4));

    await vi.waitFor(() => expect(sheet()).toBeNull());
    expect(onJumpToMessageId).toHaveBeenCalledWith('u4-unloaded');
  });

  it('reports a failing load, stays open and can be used again', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { onLoadThroughTurn } = renderSheet();
    onLoadThroughTurn.mockRejectedValue(new Error('offline'));
    openSheet();

    fireEvent.click(row(4));

    await vi.waitFor(() => expect(kit.toast).toHaveBeenCalledTimes(1));
    expect(error).toHaveBeenCalledWith('Failed to load through target turn:', expect.any(Error));
    expect(sheet()).not.toBeNull();
    expect(rowLabel(4)).toBe('unloaded');
  });

  it('ignores another choice while a turn is loading', async () => {
    const load = deferred<boolean>();
    const { onJump, onLoadThroughTurn } = renderSheet();
    onLoadThroughTurn.mockReturnValue(load.promise);
    openSheet();

    fireEvent.click(row(4));
    fireEvent.click(row(4));
    fireEvent.click(row(1));

    expect(onLoadThroughTurn).toHaveBeenCalledTimes(1);
    expect(onJump).not.toHaveBeenCalled();
    expect(sheet()).not.toBeNull();

    load.resolve(true);
    await vi.waitFor(() => expect(sheet()).toBeNull());
  });

  it('keeps the sheet open when it was given no way to load an older turn', () => {
    renderSheet({ onLoadThroughTurn: undefined });
    openSheet();

    fireEvent.click(row(4));

    expect(sheet()).not.toBeNull();
    expect(kit.toast).not.toHaveBeenCalled();
  });
});

describe('MobileTurnOutlineSheet following the outline', () => {
  it('lists a turn that joins the outline while the sheet is open', () => {
    const { update } = renderSheet();
    openSheet();
    expect(screen.queryByRole('button', { name: /^turn \{"index":5\}/ })).toBeNull();

    update({ turnOutlines: [...OUTLINES, outline(5, 'u5-unloaded', 'Step 5: a newer turn.')] });

    expect(row(5)).toHaveTextContent('Step 5: a newer turn.');
  });
});

describe('MobileTurnOutlineSheet coming back', () => {
  it('is closed again when the outline returns after it was away', () => {
    const { update } = renderSheet();
    openSheet();
    expect(sheet()).not.toBeNull();

    update({ messages: LOADED_MESSAGES.slice(0, 3), turnOutlines: undefined });
    expect(screen.queryByRole('button', { name: 'open outline' })).toBeNull();
    update({});

    expect(screen.getByRole('button', { name: 'open outline' })).toBeInTheDocument();
    expect(sheet()).toBeNull();
  });
});
