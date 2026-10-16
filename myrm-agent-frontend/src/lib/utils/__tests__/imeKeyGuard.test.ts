/**
 * The window-level guard for the two keys an input method owns while composing: Enter (confirms a candidate) and
 * Escape (cancels the composition).
 *
 * Real scenario: a user names a chat in the sidebar with a pinyin input method and presses Enter to pick the
 * characters, or presses Escape to drop the pinyin they typed. Neither key may reach the field's own handler, a
 * `window` level listener or a capture listener registered later (such as the one that aborts a running turn on
 * Escape), while the same keys afterwards act normally and code editors that run their own composition handling see
 * every key.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IME_CONFIRM_KEY_WINDOW_MS, installImeKeyGuard } from '../imeUtils';

/** Each test starts after the Safari confirm window of the previous one has long closed. */
let clock = Date.parse('2026-10-16T00:00:00Z');

function keydown(target: Element, init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

function field(parent: Element = document.body): HTMLInputElement {
  const input = document.createElement('input');
  parent.appendChild(input);
  return input;
}

const confirmCandidate = { key: 'Enter', keyCode: 229, isComposing: true } as const;
const cancelComposition = { key: 'Escape', keyCode: 229, isComposing: true } as const;
const plainEnter = { key: 'Enter', keyCode: 13 } as const;
const plainEscape = { key: 'Escape', keyCode: 27 } as const;

describe('installImeKeyGuard', () => {
  const atTarget = vi.fn();
  const atDocument = vi.fn();
  const atWindowBubble = vi.fn();
  const atWindowCapture = vi.fn();
  let uninstall: () => void;

  beforeEach(() => {
    clock += 10_000;
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(clock);
    [atTarget, atDocument, atWindowBubble, atWindowCapture].forEach((fn) => fn.mockClear());
    uninstall = installImeKeyGuard();
    // Registered after the guard, the way feature hooks register theirs when they mount.
    window.addEventListener('keydown', atWindowCapture, true);
    document.addEventListener('keydown', atDocument, true);
    window.addEventListener('keydown', atWindowBubble);
  });

  afterEach(() => {
    uninstall();
    window.removeEventListener('keydown', atWindowCapture, true);
    document.removeEventListener('keydown', atDocument, true);
    window.removeEventListener('keydown', atWindowBubble);
    document.body.replaceChildren();
    vi.useRealTimers();
  });

  function expectNothingReceived(): void {
    expect(atTarget).not.toHaveBeenCalled();
    expect(atDocument).not.toHaveBeenCalled();
    expect(atWindowBubble).not.toHaveBeenCalled();
    expect(atWindowCapture).not.toHaveBeenCalled();
  }

  function expectReceivedOnce(): void {
    expect(atTarget).toHaveBeenCalledTimes(1);
    expect(atDocument).toHaveBeenCalledTimes(1);
    expect(atWindowBubble).toHaveBeenCalledTimes(1);
    expect(atWindowCapture).toHaveBeenCalledTimes(1);
  }

  it.each([
    ['the Enter that confirms a candidate', confirmCandidate],
    ['the Escape that cancels a composition', cancelComposition],
  ])('keeps %s from every handler on the page', (_name, composing) => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    keydown(input, composing);

    expectNothingReceived();
  });

  it.each([
    ['Enter', plainEnter],
    ['Escape', plainEscape],
  ])('lets a plain %s through to every handler', (_name, plain) => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    keydown(input, plain);

    expectReceivedOnce();
  });

  it.each([
    ['Enter', confirmCandidate],
    ['Escape', cancelComposition],
  ])('leaves the browser default of the composing %s alone', (_name, composing) => {
    const event = keydown(field(), composing);

    expect(event.defaultPrevented).toBe(false);
  });

  it('only concerns Enter and Escape: other keys pressed while composing still arrive', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    keydown(input, { key: 'ArrowDown', keyCode: 229, isComposing: true });

    expect(atTarget).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['Enter', plainEnter],
    ['Escape', plainEscape],
  ])('holds back the %s Safari sends right after compositionend, but not a later one', (_name, plain) => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    document.dispatchEvent(new Event('compositionend'));
    keydown(input, plain);
    expect(atTarget).not.toHaveBeenCalled();

    vi.setSystemTime(clock + IME_CONFIRM_KEY_WINDOW_MS + 1);
    keydown(input, plain);
    expect(atTarget).toHaveBeenCalledTimes(1);
  });

  it.each(['monaco-editor', 'cm-editor'])('never intervenes inside a %s, which handles composition itself', (host) => {
    const editor = document.createElement('div');
    editor.className = host;
    document.body.appendChild(editor);
    const input = field(editor);
    input.addEventListener('keydown', atTarget);

    keydown(input, confirmCandidate);
    keydown(input, cancelComposition);

    expect(atTarget).toHaveBeenCalledTimes(2);
  });

  it('ignores a second install without removing the first, and can be removed and installed again', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);
    const again = installImeKeyGuard();
    again();

    keydown(input, confirmCandidate);
    expect(atTarget).not.toHaveBeenCalled();

    uninstall();
    keydown(input, confirmCandidate);
    expect(atTarget).toHaveBeenCalledTimes(1);

    uninstall = installImeKeyGuard();
    keydown(input, confirmCandidate);
    expect(atTarget).toHaveBeenCalledTimes(1);
  });
});
