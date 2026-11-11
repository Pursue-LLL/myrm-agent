import { act, fireEvent, render, screen } from '@testing-library/react';
import { type ComponentProps, createRef } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const prewarm = vi.hoisted(() => ({
  triggerPrewarm: vi.fn(),
  cancelPrewarm: vi.fn(),
  shouldPrewarm: true,
}));
vi.mock('@/hooks/chat/useChatTurnPrewarm', () => ({ useChatTurnPrewarm: () => prewarm }));
vi.mock('@/services/memory', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/memory')>()),
  reportUserActivity: vi.fn().mockResolvedValue(undefined),
}));

import { ComposerTextarea } from '../ComposerTextarea';

const BLUR_SETTLE_MS = 120;

function stubViewport(keyboardAtHand: boolean) {
  const matchMedia = vi.fn((query: string) => ({ matches: keyboardAtHand, media: query }));
  vi.stubGlobal('matchMedia', matchMedia);
  return matchMedia;
}

function renderTextarea(props: Partial<ComponentProps<typeof ComposerTextarea>> = {}) {
  const inputRef = createRef<HTMLTextAreaElement>();
  const view = render(
    <div data-chat-composer>
      <ComposerTextarea
        inputRef={inputRef}
        value=""
        loading={false}
        hasFiles={false}
        expanded={false}
        onChange={vi.fn()}
        onPaste={vi.fn()}
        onCaretMove={vi.fn()}
        {...props}
      />
    </div>,
  );
  const textarea = view.container.querySelector<HTMLTextAreaElement>('textarea[data-chat-input]');
  if (!textarea) {
    throw new Error('the composer textarea did not render');
  }
  return { ...view, textarea };
}

/** Moves the cursor out the way a viewer does, then lets the blur settle. */
const leave = (textarea: HTMLTextAreaElement) => {
  act(() => {
    textarea.blur();
  });
  act(() => {
    vi.advanceTimersByTime(BLUR_SETTLE_MS);
  });
};

describe('ComposerTextarea focus on mount', () => {
  beforeEach(() => {
    prewarm.triggerPrewarm.mockReset();
    prewarm.cancelPrewarm.mockReset();
    prewarm.shouldPrewarm = true;
    stubViewport(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('puts the cursor in the text area on mount, without scrolling, where a keyboard is at hand', () => {
    const matchMedia = stubViewport(true);
    const focus = vi.spyOn(HTMLElement.prototype, 'focus');

    const { textarea } = renderTextarea({ focusOnMount: true });

    expect(document.activeElement).toBe(textarea);
    expect(focus).toHaveBeenCalledWith({ preventScroll: true });
    expect(matchMedia).toHaveBeenCalledWith('(min-width: 640px) and (pointer: fine)');
  });

  it('leaves the cursor alone unless asked', () => {
    const { textarea } = renderTextarea();

    expect(document.activeElement).not.toBe(textarea);
  });

  it('does not open an on-screen keyboard on a phone or a touch screen', () => {
    stubViewport(false);

    const { textarea } = renderTextarea({ focusOnMount: true });

    expect(document.activeElement).not.toBe(textarea);
  });

  it('does not take the cursor from another text field the viewer is typing in', () => {
    const other = document.createElement('input');
    document.body.append(other);
    other.focus();

    const { textarea } = renderTextarea({ focusOnMount: true });

    expect(document.activeElement).toBe(other);
    expect(document.activeElement).not.toBe(textarea);
    other.remove();
  });

  it('copes with a browser that has no media queries', () => {
    vi.stubGlobal('matchMedia', undefined);

    expect(() => renderTextarea({ focusOnMount: true })).not.toThrow();
  });

  it('warms the next turn when the cursor lands, like any other focus', () => {
    renderTextarea({ focusOnMount: true });

    expect(prewarm.triggerPrewarm).toHaveBeenCalledTimes(1);
  });
});

describe('ComposerTextarea releasing the warm turn on blur', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    prewarm.triggerPrewarm.mockReset();
    prewarm.cancelPrewarm.mockReset();
    prewarm.shouldPrewarm = true;
    stubViewport(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('keeps it when an automatic focus ends before the viewer touched the text area', () => {
    const { textarea } = renderTextarea({ focusOnMount: true });

    leave(textarea);

    expect(prewarm.cancelPrewarm).not.toHaveBeenCalled();
  });

  it.each([
    ['typing', (textarea: HTMLTextAreaElement) => fireEvent.change(textarea, { target: { value: 'a' } })],
    ['pressing it', (textarea: HTMLTextAreaElement) => fireEvent.pointerDown(textarea)],
    ['a key press', (textarea: HTMLTextAreaElement) => fireEvent.keyDown(textarea, { key: 'Shift' })],
  ])('releases it once the viewer engaged by %s', (_name, engage) => {
    const { textarea } = renderTextarea({ focusOnMount: true });

    engage(textarea);
    leave(textarea);

    expect(prewarm.cancelPrewarm).toHaveBeenCalledTimes(1);
  });

  it('releases it after any blur when the cursor was not placed automatically', () => {
    const { textarea } = renderTextarea();
    act(() => {
      textarea.focus();
    });

    leave(textarea);

    expect(prewarm.cancelPrewarm).toHaveBeenCalledTimes(1);
  });

  it('keeps it while the cursor only moves to another control of the composer', () => {
    const { textarea, container } = renderTextarea();
    const sibling = document.createElement('button');
    container.querySelector('[data-chat-composer]')?.append(sibling);
    act(() => {
      textarea.focus();
    });

    act(() => {
      sibling.focus();
    });
    act(() => {
      vi.advanceTimersByTime(BLUR_SETTLE_MS);
    });

    expect(prewarm.cancelPrewarm).not.toHaveBeenCalled();
  });
});

describe('ComposerTextarea accessible name', () => {
  beforeEach(() => {
    stubViewport(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  // The placeholder is a hint that changes with the busy state and a previewed history entry; the name must not.
  it.each<[state: string, props: Partial<ComponentProps<typeof ComposerTextarea>>]>([
    ['idle', {}],
    ['expanded', { expanded: true }],
    ['busy', { loading: true }],
    ['previewing a history entry', { ghostText: 'an earlier prompt' }],
  ])('is the same while %s', (_state, props) => {
    const { textarea } = renderTextarea(props);

    expect(screen.getByRole('textbox', { name: 'input.label' })).toBe(textarea);
    expect(textarea.placeholder).not.toBe('input.label');
  });
});

describe('ComposerTextarea colors', () => {
  // Against the composer surface the placeholder at half opacity measured 2.0:1 in the light palette and 2.7:1 in the dark one;
  // the full muted-foreground token measures 5.1:1 and 7.0:1. Typed text stays on the foreground token so imported palettes recolor it.
  it('keeps the placeholder readable and the text on theme tokens', () => {
    const { textarea } = renderTextarea();
    const classes = Array.from(textarea.classList);

    expect(classes).toEqual(expect.arrayContaining(['placeholder:text-muted-foreground', 'text-foreground']));
    expect(
      classes.filter((name) => /^placeholder:text-muted-foreground\/|^(dark:)?text-(black|white)/.test(name)),
    ).toEqual([]);
  });
});
