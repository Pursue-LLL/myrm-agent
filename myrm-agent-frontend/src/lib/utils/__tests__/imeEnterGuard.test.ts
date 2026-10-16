/**
 * The document-level guard for the Enter that confirms an input-method candidate.
 *
 * Real scenario: a user names a chat in the sidebar with a pinyin input method and presses Enter to pick the
 * characters. That Enter must reach neither the rename field's own handler nor a `window` level listener, while a
 * plain Enter afterwards still submits, and code editors that run their own composition handling see every key.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { IME_CONFIRM_ENTER_WINDOW_MS, installImeEnterGuard } from '../imeUtils';

/** Each test starts after the Safari confirm window of the previous one has long closed. */
let clock = Date.parse('2026-10-16T00:00:00Z');

function keydown(target: Element, init: KeyboardEventInit): void {
  target.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init }));
}

function field(parent: Element = document.body): HTMLInputElement {
  const input = document.createElement('input');
  parent.appendChild(input);
  return input;
}

const confirmCandidate = { key: 'Enter', keyCode: 229, isComposing: true } as const;
const plainEnter = { key: 'Enter', keyCode: 13 } as const;

describe('installImeEnterGuard', () => {
  const atTarget = vi.fn();
  const atWindow = vi.fn();
  let uninstall: () => void;

  beforeEach(() => {
    clock += 10_000;
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(clock);
    atTarget.mockClear();
    atWindow.mockClear();
    window.addEventListener('keydown', atWindow);
    uninstall = installImeEnterGuard();
  });

  afterEach(() => {
    uninstall();
    window.removeEventListener('keydown', atWindow);
    document.body.replaceChildren();
    vi.useRealTimers();
  });

  it('keeps the Enter that confirms a candidate from the field handler and from window listeners', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    keydown(input, confirmCandidate);

    expect(atTarget).not.toHaveBeenCalled();
    expect(atWindow).not.toHaveBeenCalled();
  });

  it('lets a plain Enter through to every handler', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    keydown(input, plainEnter);

    expect(atTarget).toHaveBeenCalledTimes(1);
    expect(atWindow).toHaveBeenCalledTimes(1);
  });

  it('leaves the browser default of the confirming Enter alone', () => {
    const input = field();
    const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...confirmCandidate });

    input.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
  });

  it('only concerns Enter: other keys pressed while composing still arrive', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    keydown(input, { key: 'ArrowDown', keyCode: 229, isComposing: true });

    expect(atTarget).toHaveBeenCalledTimes(1);
  });

  it('holds back the Enter Safari sends right after compositionend, but not a later one', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);

    document.dispatchEvent(new Event('compositionend'));
    keydown(input, plainEnter);
    expect(atTarget).not.toHaveBeenCalled();

    vi.setSystemTime(clock + IME_CONFIRM_ENTER_WINDOW_MS + 1);
    keydown(input, plainEnter);
    expect(atTarget).toHaveBeenCalledTimes(1);
  });

  it.each(['monaco-editor', 'cm-editor'])('never intervenes inside a %s, which handles composition itself', (host) => {
    const editor = document.createElement('div');
    editor.className = host;
    document.body.appendChild(editor);
    const input = field(editor);
    input.addEventListener('keydown', atTarget);

    keydown(input, confirmCandidate);

    expect(atTarget).toHaveBeenCalledTimes(1);
  });

  it('ignores a second install without removing the first, and can be removed and installed again', () => {
    const input = field();
    input.addEventListener('keydown', atTarget);
    const again = installImeEnterGuard();
    again();

    keydown(input, confirmCandidate);
    expect(atTarget).not.toHaveBeenCalled();

    uninstall();
    keydown(input, confirmCandidate);
    expect(atTarget).toHaveBeenCalledTimes(1);

    uninstall = installImeEnterGuard();
    keydown(input, confirmCandidate);
    expect(atTarget).toHaveBeenCalledTimes(1);
  });
});
