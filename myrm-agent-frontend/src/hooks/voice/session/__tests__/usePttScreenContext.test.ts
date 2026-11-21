import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { usePttScreenContext } from '../usePttScreenContext';
import type { PttScreenContext } from '../../useVoicePttListener';

function makeContext(overrides: Partial<PttScreenContext> = {}): PttScreenContext {
  return {
    screenshot: 'b64-shot',
    windowTitle: 'Editor',
    extractedText: 'screen words',
    selectedText: 'picked words',
    timestamp: Date.now(),
    ...overrides,
  };
}

function emitContext(detail: PttScreenContext) {
  act(() => {
    window.dispatchEvent(new CustomEvent('voice-ptt-context', { detail }));
  });
}

describe('usePttScreenContext', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns the transcript untouched when no screen context was captured', async () => {
    const { result } = renderHook(() => usePttScreenContext('toggle'));

    await expect(result.current('hello')).resolves.toEqual({ text: 'hello', visionFrames: undefined });
  });

  it('fuses window title, selected text and the screenshot into the message', async () => {
    const { result } = renderHook(() => usePttScreenContext('push-to-talk'));
    emitContext(makeContext());

    await expect(result.current('what is this')).resolves.toEqual({
      text: '[Active Window: Editor]\n[Selected Text: picked words]\n\nwhat is this',
      visionFrames: ['b64-shot'],
    });
  });

  it('falls back to the extracted screen text when nothing is selected', async () => {
    const { result } = renderHook(() => usePttScreenContext('push-to-talk'));
    emitContext(makeContext({ selectedText: '  ' }));

    const payload = await result.current('summarize');

    expect(payload.text).toBe('[Active Window: Editor]\n[Screen Text: screen words]\n\nsummarize');
  });

  it('uses each captured context once', async () => {
    const { result } = renderHook(() => usePttScreenContext('toggle'));
    emitContext(makeContext());

    await result.current('first');

    await expect(result.current('second')).resolves.toEqual({ text: 'second', visionFrames: undefined });
  });

  it('ignores a context older than 30 seconds', async () => {
    const { result } = renderHook(() => usePttScreenContext('toggle'));
    emitContext(makeContext({ timestamp: Date.now() - 31_000 }));

    await expect(result.current('stale')).resolves.toEqual({ text: 'stale', visionFrames: undefined });
  });

  it('drops the stored context when a new PTT press starts', async () => {
    const { result } = renderHook(() => usePttScreenContext('toggle'));
    emitContext(makeContext());
    act(() => {
      window.dispatchEvent(new Event('voice-ptt-start'));
    });

    await expect(result.current('after press')).resolves.toEqual({ text: 'after press', visionFrames: undefined });
  });

  it('ignores a context event that carries no screenshot or text', async () => {
    const { result } = renderHook(() => usePttScreenContext('toggle'));
    emitContext(makeContext({ screenshot: '', extractedText: '', selectedText: undefined }));

    await expect(result.current('empty')).resolves.toEqual({ text: 'empty', visionFrames: undefined });
  });

  it('push-to-talk waits for a screenshot that arrives after the transcript', async () => {
    const { result } = renderHook(() => usePttScreenContext('push-to-talk'));

    const pending = result.current('late shot');
    emitContext(makeContext());

    await expect(pending).resolves.toMatchObject({ visionFrames: ['b64-shot'] });
  });

  it('push-to-talk gives up after the 250 ms barrier', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => usePttScreenContext('push-to-talk'));

    const pending = result.current('no shot');
    await vi.advanceTimersByTimeAsync(250);

    await expect(pending).resolves.toEqual({ text: 'no shot', visionFrames: undefined });
  });
});
