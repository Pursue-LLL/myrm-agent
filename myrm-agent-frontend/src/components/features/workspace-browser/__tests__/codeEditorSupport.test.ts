/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { preloadMonacoEditor } = vi.hoisted(() => ({ preloadMonacoEditor: vi.fn() }));
vi.mock('@/lib/utils/componentPreloader', () => ({ preloadMonacoEditor }));

import { preloadCodeEditor, supportsCodeEditor, useSupportsCodeEditor } from '../codeEditorSupport';

type Listener = () => void;

/** A `matchMedia` whose answer the test flips by hand; every query gets the same answer. */
function installMatchMedia(initial: boolean) {
  let matches = initial;
  const listeners = new Set<Listener>();
  const queries: string[] = [];
  window.matchMedia = ((query: string) => {
    queries.push(query);
    return {
      get matches() {
        return matches;
      },
      addEventListener: (_type: string, listener: Listener) => listeners.add(listener),
      removeEventListener: (_type: string, listener: Listener) => listeners.delete(listener),
    } as unknown as MediaQueryList;
  }) as typeof window.matchMedia;
  return {
    queries,
    listenerCount: () => listeners.size,
    flip(next: boolean) {
      matches = next;
      listeners.forEach((listener) => listener());
    },
  };
}

describe('code editor support', () => {
  const original = window.matchMedia;

  beforeEach(() => {
    preloadMonacoEditor.mockClear();
  });

  afterEach(() => {
    window.matchMedia = original;
  });

  it('is off where the browser cannot answer a media query', () => {
    window.matchMedia = undefined as unknown as typeof window.matchMedia;

    expect(supportsCodeEditor()).toBe(false);
  });

  it('asks for a wide window with a precise pointer: touch screens and narrow windows keep the textarea', () => {
    const media = installMatchMedia(true);

    expect(supportsCodeEditor()).toBe(true);
    expect(media.queries[0]).toContain('min-width: 769px');
    expect(media.queries[0]).toContain('pointer: fine');
  });

  it('follows the window while it is open, and lets go when it unmounts', () => {
    const media = installMatchMedia(false);
    const { result, unmount } = renderHook(() => useSupportsCodeEditor());
    expect(result.current).toBe(false);

    act(() => media.flip(true));
    expect(result.current).toBe(true);

    unmount();
    expect(media.listenerCount()).toBe(0);
  });

  it.each([true, false])('answers on the very first render when the answer is %s', (answer) => {
    installMatchMedia(answer);
    const renders: boolean[] = [];

    renderHook(() => {
      const supported = useSupportsCodeEditor();
      renders.push(supported);
      return supported;
    });

    // No flash of the wrong editor, and no bundle fetched for a touch screen that never shows it.
    expect(renders).toEqual([answer]);
  });

  it('preloads the editor bundle only where it would be used', () => {
    installMatchMedia(false);
    preloadCodeEditor();
    expect(preloadMonacoEditor).not.toHaveBeenCalled();

    installMatchMedia(true);
    preloadCodeEditor();
    expect(preloadMonacoEditor).toHaveBeenCalledTimes(1);
  });
});
