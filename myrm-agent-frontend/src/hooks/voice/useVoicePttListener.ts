'use client';

/**
 * [INPUT]
 * - Tauri event "voice-ptt-start" (global shortcut Pressed)
 * - Tauri event "voice-ptt-stop" (global shortcut Released)
 * - Tauri event "voice-ptt-context" (screenshot + text of active window at PTT press)
 *
 * [OUTPUT]
 * - DOM CustomEvent "voice-ptt-start" / "voice-ptt-stop" (consumed by useSpeechInput)
 * - DOM CustomEvent "voice-ptt-context" with PttScreenContext detail (consumed by useVoiceSession)
 * - PttScreenContext type export
 *
 * [POS]
 * Bridges Tauri-side global PTT shortcut events to frontend DOM events.
 * This allows useSpeechInput and useVoiceSession to respond to the
 * global push-to-talk hotkey without direct Tauri coupling.
 */

import { useEffect } from 'react';
import { isTauriRuntime } from '@/lib/deploy-mode';

/** PTT 屏幕上下文事件的 payload 类型 */
export interface PttScreenContext {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  timestamp: number;
}

export function useVoicePttListener() {
  useEffect(() => {
    if (!isTauriRuntime()) return;

    let unlistenStart: (() => void) | undefined;
    let unlistenStop: (() => void) | undefined;
    let unlistenContext: (() => void) | undefined;

    const setup = async () => {
      try {
        const { listen } = await import('@tauri-apps/api/event');

        unlistenStart = await listen('voice-ptt-start', () => {
          window.dispatchEvent(new CustomEvent('voice-ptt-start', { cancelable: true }));
        });

        unlistenStop = await listen('voice-ptt-stop', () => {
          window.dispatchEvent(new CustomEvent('voice-ptt-stop', { cancelable: true }));
        });

        unlistenContext = await listen<PttScreenContext>('voice-ptt-context', (event) => {
          window.dispatchEvent(
            new CustomEvent('voice-ptt-context', { detail: event.payload, cancelable: true })
          );
        });
      } catch (err) {
        console.error('Failed to setup voice PTT listener:', err);
      }
    };

    setup();

    return () => {
      unlistenStart?.();
      unlistenStop?.();
      unlistenContext?.();
    };
  }, []);
}
