'use client';

/**
 * [INPUT]
 * hooks/voice/session/types (POS: Voice session state and mode vocabulary)
 *
 * [OUTPUT]
 * useSessionEvents: Connects the voice session to window events (toggle / interrupt / replay in, state broadcast out)
 *
 * [POS]
 * Window event bridge of the voice session. Satellites (Tauri Pet companion, global shortcuts) drive the session through
 * `myrm-voice-toggle` / `myrm-voice-interrupt` / `myrm-voice-replay` and observe it through `myrm-voice-state-update`.
 * It is the only listener of these events: a second one anywhere would act on the same event twice.
 */

import { useEffect, type MutableRefObject } from 'react';
import type { VoiceSessionState } from './types';

interface UseSessionEventsOptions {
  sessionState: VoiceSessionState;
  audioLevel: number;
  sessionActiveRef: MutableRefObject<boolean>;
  startSession: () => void;
  stopSession: () => void;
  interruptTTS: () => void;
  replayLastTTS: () => void;
}

export function useSessionEvents({
  sessionState,
  audioLevel,
  sessionActiveRef,
  startSession,
  stopSession,
  interruptTTS,
  replayLastTTS,
}: UseSessionEventsOptions): void {
  // External event bus listeners (from Tauri Pet companion or global shortcuts)
  useEffect(() => {
    const handleToggle = () => {
      if (sessionActiveRef.current) {
        stopSession();
      } else {
        startSession();
      }
    };

    const handleInterrupt = () => {
      interruptTTS();
    };

    const handleReplay = () => {
      replayLastTTS();
    };

    window.addEventListener('myrm-voice-toggle', handleToggle);
    window.addEventListener('myrm-voice-interrupt', handleInterrupt);
    window.addEventListener('myrm-voice-replay', handleReplay);

    return () => {
      window.removeEventListener('myrm-voice-toggle', handleToggle);
      window.removeEventListener('myrm-voice-interrupt', handleInterrupt);
      window.removeEventListener('myrm-voice-replay', handleReplay);
    };
  }, [sessionActiveRef, startSession, stopSession, interruptTTS, replayLastTTS]);

  // Broadcast unified voice state for satellites / companion / Pet overlay
  useEffect(() => {
    const mappedState =
      sessionState === 'inactive'
        ? 'idle'
        : sessionState === 'speaking'
          ? 'speaking'
          : sessionState === 'processing'
            ? 'processing'
            : 'listening';

    window.dispatchEvent(
      new CustomEvent('myrm-voice-state-update', {
        detail: {
          voiceState: mappedState,
          audioLevel,
        },
      }),
    );
  }, [sessionState, audioLevel]);
}
