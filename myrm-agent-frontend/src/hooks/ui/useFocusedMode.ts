'use client';

import { useState, useEffect } from 'react';

/**
 * Detects whether the current page is opened in "focused mode" —
 * a standalone session window without sidebar/navbar (Tauri desktop detach).
 *
 * Triggered by URL query parameter `?mode=focused`, set by the Tauri
 * `open_session_window` IPC command.
 */
export function useFocusedMode(): boolean {
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setFocused(params.get('mode') === 'focused');
  }, []);

  return focused;
}
