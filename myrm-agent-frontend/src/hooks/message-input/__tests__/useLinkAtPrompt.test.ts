import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLinkAtPrompt } from '../useLinkAtPrompt';

const STORAGE_KEY = 'dontRemindLinkDialog';

function setup(initialText = '') {
  const setInputMessage = vi.fn();
  const textarea = document.createElement('textarea');
  document.body.appendChild(textarea);
  const view = renderHook(
    ({ inputMessage }: { inputMessage: string }) =>
      useLinkAtPrompt({ inputMessage, setInputMessage, inputRef: { current: textarea } }),
    { initialProps: { inputMessage: initialText } },
  );
  const detect = (text: string) => act(() => view.result.current.detectLink(text));
  return { ...view, detect, setInputMessage, textarea };
}

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('useLinkAtPrompt asking', () => {
  it('stays quiet for text without a link and for a link that already has its @', () => {
    const { result, detect } = setup();

    detect('nothing to see here, not even example.com');
    detect('read @https://example.com please');
    detect('a link that is still being typed: https://');

    expect(result.current.showLinkDialog).toBe(false);
  });

  it.each(['see https://example.com', 'http://example.com', 'first line\nhttps://example.com/a?b=1'])(
    'asks when the text holds a link without an @: %j',
    (text) => {
      const { result, detect } = setup();

      detect(text);

      expect(result.current.showLinkDialog).toBe(true);
    },
  );

  it('closes after either answer', () => {
    const { result, detect } = setup('see https://example.com');
    detect('see https://example.com');
    act(() => result.current.handleSkipAtSymbol());
    expect(result.current.showLinkDialog).toBe(false);

    const second = setup('see https://example.com');
    second.detect('see https://example.com');
    act(() => second.result.current.handleAddAtSymbol());
    expect(second.result.current.showLinkDialog).toBe(false);
  });

  it('asks only once per message, however the user answers and keeps editing', () => {
    const { result, detect } = setup('see https://example.com');
    detect('see https://example.com');
    act(() => result.current.handleSkipAtSymbol());

    detect('see https://example.com now');
    detect('see https://example.com now and https://other.example');

    expect(result.current.showLinkDialog).toBe(false);
  });

  it('asks again once the message no longer holds a link, for instance after it was sent', () => {
    const { result, detect, rerender } = setup('see https://example.com');
    detect('see https://example.com');
    act(() => result.current.handleSkipAtSymbol());

    rerender({ inputMessage: 'see https://example.com and more' });
    detect('see https://example.com and more');
    expect(result.current.showLinkDialog).toBe(false);

    rerender({ inputMessage: '' });
    detect('https://next.example');

    expect(result.current.showLinkDialog).toBe(true);
  });
});

describe('useLinkAtPrompt adding the @', () => {
  const link = 'https://a.example/x';

  it.each([
    ['in the middle of a text', `read ${link} now`, `read @${link} now`, 5],
    ['at the very start', `${link} now`, `@${link} now`, 0],
    ['after a line break', `go\n${link}`, `go\n@${link}`, 3],
  ])('puts it right before a link %s', (_where, text, expected) => {
    const { result, detect, setInputMessage } = setup(text);
    detect(text);

    act(() => result.current.handleAddAtSymbol());

    expect(setInputMessage).toHaveBeenCalledExactlyOnceWith(expected);
  });

  it.each([
    { where: 'the start', before: () => 0 },
    { where: 'the end', before: (text: string) => text.length },
  ])('leaves the caret right after the link and focuses the input, whether it was at $where', ({ before }) => {
    const text = `read ${link} now`;
    const { result, detect, textarea } = setup(text);
    detect(text);
    act(() => result.current.handleAddAtSymbol());
    textarea.value = `read @${link} now`;
    textarea.setSelectionRange(before(textarea.value), before(textarea.value));

    act(() => vi.runAllTimers());

    expect(textarea.selectionStart).toBe(`read @${link}`.length);
    expect(textarea.selectionEnd).toBe(`read @${link}`.length);
    expect(document.activeElement).toBe(textarea);
  });

  it('puts the @ before the first of several links', () => {
    const text = `${link} and https://b.example`;
    const { result, detect, setInputMessage } = setup(text);
    detect(text);

    act(() => result.current.handleAddAtSymbol());

    expect(setInputMessage).toHaveBeenCalledExactlyOnceWith(`@${link} and https://b.example`);
  });

  it('writes nothing when no link was ever found', () => {
    const { result, setInputMessage } = setup('plain text');

    act(() => result.current.handleAddAtSymbol());

    expect(setInputMessage).not.toHaveBeenCalled();
    expect(result.current.showLinkDialog).toBe(false);
  });

  it('writes nothing after the question was answered with no', () => {
    const { result, detect, setInputMessage } = setup(`see ${link}`);
    detect(`see ${link}`);
    act(() => result.current.handleSkipAtSymbol());

    act(() => result.current.handleAddAtSymbol());

    expect(setInputMessage).not.toHaveBeenCalled();
  });
});

describe('useLinkAtPrompt not asking again', () => {
  it('remembers a ticked "do not remind me" whichever way the question is answered', () => {
    for (const answer of ['handleSkipAtSymbol', 'handleAddAtSymbol'] as const) {
      localStorage.clear();
      const { result, detect } = setup('see https://example.com');
      detect('see https://example.com');
      act(() => result.current.setDontRemindAgain(true));

      act(() => result.current[answer]());

      expect(localStorage.getItem(STORAGE_KEY)).toBe('true');
    }
  });

  it('remembers nothing unless the box was ticked', () => {
    const { result, detect } = setup('see https://example.com');
    detect('see https://example.com');

    act(() => result.current.handleAddAtSymbol());

    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('never asks while the box is ticked, even before it was saved', () => {
    const { result, detect } = setup();
    act(() => result.current.setDontRemindAgain(true));

    detect('see https://example.com');

    expect(result.current.showLinkDialog).toBe(false);
  });

  it('starts out ticked and silent when the choice was saved earlier', () => {
    localStorage.setItem(STORAGE_KEY, 'true');
    const { result, detect } = setup();

    detect('see https://example.com');

    expect(result.current.dontRemindAgain).toBe(true);
    expect(result.current.showLinkDialog).toBe(false);
  });

  it('starts out unticked for anything else that was saved', () => {
    localStorage.setItem(STORAGE_KEY, 'false');
    const { result } = setup();

    expect(result.current.dontRemindAgain).toBe(false);
  });
});
