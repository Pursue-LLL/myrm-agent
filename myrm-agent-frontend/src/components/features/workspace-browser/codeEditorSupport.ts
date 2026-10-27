'use client';

/**
 * Where the workspace file editor is the full code editor (Monaco) and where it stays the plain textarea.
 *
 * [INPUT]
 * - window.matchMedia: the width of the window and the kind of pointer
 * - preloadMonacoEditor from @/lib/utils/componentPreloader (POS: fetches the editor bundle ahead of its first use)
 *
 * [OUTPUT]
 * - supportsCodeEditor: the answer right now
 * - useSupportsCodeEditor: the answer, kept current while the window changes
 * - preloadCodeEditor: starts fetching the editor bundle, only where the code editor would be used
 *
 * [POS]
 * The code editor is a keyboard-and-mouse tool. A touch screen or a narrow window gets the textarea, which the
 * system keyboard, selection handles and input methods handle natively. Decided from the first render on, so a
 * touch screen never starts downloading an editor it will not show.
 */

import { useSyncExternalStore } from 'react';
import { preloadMonacoEditor } from '@/lib/utils/componentPreloader';

// 768px is the width the app already treats as a phone (`useIsMobile`).
const CODE_EDITOR_QUERY = '(min-width: 769px) and (pointer: fine)';

export function supportsCodeEditor(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(CODE_EDITOR_QUERY).matches
    : false;
}

function subscribe(notify: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {};
  }
  const query = window.matchMedia(CODE_EDITOR_QUERY);
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
}

export function useSupportsCodeEditor(): boolean {
  return useSyncExternalStore(subscribe, supportsCodeEditor, () => false);
}

/** Meant for the moment the user reaches for the Edit button: the bundle is then there by the time it is clicked. */
export function preloadCodeEditor(): void {
  if (supportsCodeEditor()) {
    void preloadMonacoEditor();
  }
}
