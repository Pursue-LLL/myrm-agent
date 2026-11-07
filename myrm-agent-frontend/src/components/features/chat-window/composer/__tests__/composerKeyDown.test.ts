import type { KeyboardEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { ContextChipItem } from '@/hooks/message-input/useComposerContextChips';

import { type ComposerKeyDownContext, handleComposerKeyDown } from '../composerKeyDown';

type Press = Partial<Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'shiftKey' | 'altKey'>> & {
  composing?: boolean;
};

function press({ composing = false, ...keys }: Press) {
  const event = {
    key: 'a',
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    altKey: false,
    nativeEvent: { isComposing: composing },
    preventDefault: vi.fn(),
    ...keys,
  };
  return event as unknown as KeyboardEvent & { preventDefault: ReturnType<typeof vi.fn> };
}

function makeContext(overrides: Partial<ComposerKeyDownContext> = {}): ComposerKeyDownContext {
  return {
    inputMessage: '',
    setInputMessage: vi.fn(),
    chips: [],
    loading: false,
    editorExpanded: false,
    setEditorExpanded: vi.fn(),
    showCommandPalette: false,
    onCommandKeyDown: vi.fn(),
    showReferenceMention: false,
    onReferenceMentionKeyDown: vi.fn(() => false),
    inputHistory: {
      popup: { open: false, entries: [], activeIndex: 0 },
      handleKeyDown: vi.fn(() => false),
      confirm: vi.fn(),
    },
    submit: vi.fn(),
    queue: vi.fn(),
    ...overrides,
  };
}

const chip = (id: string, isRemovable: boolean, onRemove?: () => void): ContextChipItem => ({
  id,
  category: 'mention',
  label: id,
  iconType: 'mention',
  isRemovable,
  onRemove,
});

describe('handleComposerKeyDown', () => {
  it('ignores every key while an IME is composing, even when a route would take it', () => {
    const ctx = makeContext({ showCommandPalette: true });

    handleComposerKeyDown(press({ key: 'Enter', composing: true }), ctx);

    expect(ctx.onCommandKeyDown).not.toHaveBeenCalled();
    expect(ctx.submit).not.toHaveBeenCalled();
  });

  it('removes the last removable chip on Backspace in an empty input, before any other route', () => {
    const earlier = vi.fn();
    const later = vi.fn();
    const ctx = makeContext({
      chips: [chip('a', true, earlier), chip('b', true, later), chip('c', false)],
      showCommandPalette: true,
    });
    const event = press({ key: 'Backspace' });

    handleComposerKeyDown(event, ctx);

    expect(later).toHaveBeenCalledTimes(1);
    expect(earlier).not.toHaveBeenCalled();
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(ctx.onCommandKeyDown).not.toHaveBeenCalled();
  });

  it('keeps Backspace for the text when the input has text or no chip can be removed', () => {
    const onRemove = vi.fn();
    const withText = makeContext({ inputMessage: 'x', chips: [chip('a', true, onRemove)] });
    const noRemovable = makeContext({ chips: [chip('a', false, onRemove), chip('b', true)] });
    const event = press({ key: 'Backspace' });

    handleComposerKeyDown(event, withText);
    handleComposerKeyDown(event, noRemovable);

    expect(onRemove).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it('closes the full-screen editor on Escape only while it is open', () => {
    const open = makeContext({ editorExpanded: true });
    const closed = makeContext({ editorExpanded: false });
    const event = press({ key: 'Escape' });

    handleComposerKeyDown(event, closed);
    expect(closed.setEditorExpanded).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();

    handleComposerKeyDown(event, open);
    expect(open.setEditorExpanded).toHaveBeenCalledWith(false);
    expect(event.preventDefault).toHaveBeenCalledTimes(1);
  });

  it('toggles the full-screen editor on Ctrl or Cmd with Shift and Enter without sending', () => {
    const ctx = makeContext();

    handleComposerKeyDown(press({ key: 'Enter', ctrlKey: true, shiftKey: true }), ctx);
    handleComposerKeyDown(press({ key: 'Enter', metaKey: true, shiftKey: true }), ctx);

    const toggle = vi.mocked(ctx.setEditorExpanded).mock.calls[0][0] as (expanded: boolean) => boolean;
    expect(vi.mocked(ctx.setEditorExpanded)).toHaveBeenCalledTimes(2);
    expect([toggle(false), toggle(true)]).toEqual([true, false]);
    expect(ctx.submit).not.toHaveBeenCalled();
  });

  it('gives the slash palette every key while it is open, and nothing below it', () => {
    const ctx = makeContext({ showCommandPalette: true, showReferenceMention: true });

    handleComposerKeyDown(press({ key: 'Enter' }), ctx);

    expect(ctx.onCommandKeyDown).toHaveBeenCalledTimes(1);
    expect(ctx.onReferenceMentionKeyDown).not.toHaveBeenCalled();
    expect(ctx.inputHistory.handleKeyDown).not.toHaveBeenCalled();
    expect(ctx.submit).not.toHaveBeenCalled();
  });

  it('falls through from the @ list to the next route unless the list consumed the key', () => {
    const consumed = makeContext({ showReferenceMention: true, onReferenceMentionKeyDown: vi.fn(() => true) });
    const ignored = makeContext({ showReferenceMention: true });

    handleComposerKeyDown(press({ key: 'ArrowDown' }), consumed);
    handleComposerKeyDown(press({ key: 'ArrowDown' }), ignored);

    expect(consumed.inputHistory.handleKeyDown).not.toHaveBeenCalled();
    expect(ignored.inputHistory.handleKeyDown).toHaveBeenCalledTimes(1);
  });

  it('confirms the highlighted history entry on Tab or Enter while its popup is open', () => {
    const popup = { open: true, entries: [], activeIndex: 0 };
    const make = (text: string | undefined) =>
      makeContext({
        inputHistory: { popup, handleKeyDown: vi.fn(() => true), confirm: vi.fn(() => text) },
      });
    const withEntry = make('earlier prompt');
    const withoutText = make(undefined);

    handleComposerKeyDown(press({ key: 'Tab' }), withEntry);
    handleComposerKeyDown(press({ key: 'Enter' }), withoutText);

    expect(withEntry.setInputMessage).toHaveBeenCalledWith('earlier prompt');
    expect(withoutText.setInputMessage).not.toHaveBeenCalled();
    expect(withEntry.submit).not.toHaveBeenCalled();
  });

  it('lets the history consume a key without confirming when the popup is closed or the key is another', () => {
    const closed = makeContext({
      inputHistory: {
        popup: { open: false, entries: [], activeIndex: 0 },
        handleKeyDown: vi.fn(() => true),
        confirm: vi.fn(),
      },
    });
    const arrow = makeContext({
      inputHistory: {
        popup: { open: true, entries: [], activeIndex: 0 },
        handleKeyDown: vi.fn(() => true),
        confirm: vi.fn(),
      },
    });

    handleComposerKeyDown(press({ key: 'Enter' }), closed);
    handleComposerKeyDown(press({ key: 'ArrowUp' }), arrow);

    expect(closed.inputHistory.confirm).not.toHaveBeenCalled();
    expect(arrow.inputHistory.confirm).not.toHaveBeenCalled();
    expect(closed.submit).not.toHaveBeenCalled();
  });

  it('sends on Enter, queues on Alt+Enter while running, and leaves Shift+Enter as a newline', () => {
    const idle = makeContext();
    const running = makeContext({ loading: true });

    handleComposerKeyDown(press({ key: 'Enter' }), idle);
    handleComposerKeyDown(press({ key: 'Enter', altKey: true }), running);
    handleComposerKeyDown(press({ key: 'Enter', shiftKey: true }), idle);

    expect(idle.submit).toHaveBeenCalledTimes(1);
    expect(idle.queue).not.toHaveBeenCalled();
    expect(running.queue).toHaveBeenCalledTimes(1);
    expect(running.submit).not.toHaveBeenCalled();
  });
});
