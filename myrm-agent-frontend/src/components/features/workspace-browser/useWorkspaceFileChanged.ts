'use client';

/**
 * One call per burst of file changes in the workspace.
 *
 * [INPUT]
 * - onChange / enabled: what to run, and whether to listen at all
 * - window event `workspace-file-changed` (POS: raised by useGlobalEvents for the server's file watch, and by the
 *   organizer after it moves files; its detail names the watched workspace in the server's spelling)
 *
 * [OUTPUT]
 * - useWorkspaceFileChanged: runs `onChange` once, FILE_CHANGE_WINDOW_MS after the first event of a burst
 * - FILE_CHANGE_WINDOW_MS: how long a burst is collected
 *
 * [POS]
 * Keeps an open file current while an agent or another program writes to the workspace. The event says only that
 * something in the workspace changed, not what, so the caller checks its own file. The window starts at the first
 * event and does not move: a trailing debounce would wait forever while a writer keeps going, and the open file
 * would never update. The detail's workspace is not compared with the caller's, because the server spells it its
 * own way (resolved symlinks); a check that finds nothing new is a few hundred bytes.
 */

import { useEffect, useRef } from 'react';

export const FILE_CHANGE_WINDOW_MS = 300;

export function useWorkspaceFileChanged(onChange: () => void, enabled: boolean): void {
  // The latest callback is read when the window ends, so a new callback never restarts a window.
  const latest = useRef(onChange);
  useEffect(() => {
    latest.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let timer: ReturnType<typeof setTimeout> | null = null;
    const onEvent = () => {
      if (timer === null) {
        timer = setTimeout(() => {
          timer = null;
          latest.current();
        }, FILE_CHANGE_WINDOW_MS);
      }
    };
    window.addEventListener('workspace-file-changed', onEvent);
    return () => {
      window.removeEventListener('workspace-file-changed', onEvent);
      if (timer !== null) {
        clearTimeout(timer);
      }
    };
  }, [enabled]);
}
