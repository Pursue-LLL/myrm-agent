'use client';

/**
 * [INPUT]
 * - Tauri event "voice-ptt-start" (global shortcut Pressed)
 * - Tauri event "voice-ptt-stop" (global shortcut Released)
 *
 * [OUTPUT]
 * - Dispatches DOM CustomEvents that useSpeechInput instances listen on
 *
 * [POS]
 * Bridges Tauri-side global PTT shortcut events to frontend DOM events.
 * This allows any active useSpeechInput instance to respond to the
 * global push-to-talk hotkey without direct Tauri coupling.
 */

import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';

export function useVoicePttListener() {
  useEffect(() => {
    if (!isTauriRuntime()) return;

    let unlistenStart: (() => void) | undefined;
    let unlistenStop: (() => void) | undefined;

    const setup = async () => {
      try {
        const { listen } = await import('@tauri-apps/api/event');

        unlistenStart = await listen('voice-ptt-start', () => {
          window.dispatchEvent(new CustomEvent('voice-ptt-start', { cancelable: true }));
        });

        unlistenStop = await listen('voice-ptt-stop', () => {
          window.dispatchEvent(new CustomEvent('voice-ptt-stop', { cancelable: true }));
        });
      } catch (err) {
        console.error('Failed to setup voice PTT listener:', err);
      }
    };

    setup();

    return () => {
      unlistenStart?.();
      unlistenStop?.();
    };
  }, []);
}
