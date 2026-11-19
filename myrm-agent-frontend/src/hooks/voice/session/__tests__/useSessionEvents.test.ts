import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSessionEvents } from '../useSessionEvents';
import type { VoiceSessionState } from '../types';

type EventsProps = Parameters<typeof useSessionEvents>[0];

function setup(overrides: Partial<EventsProps> = {}) {
  const handlers = {
    startSession: vi.fn(),
    stopSession: vi.fn(),
    interruptTTS: vi.fn(),
    replayLastTTS: vi.fn(),
  };
  const sessionActiveRef = { current: false };
  const props: EventsProps = {
    sessionState: 'inactive',
    audioLevel: 0,
    sessionActiveRef,
    ...handlers,
    ...overrides,
  };
  const hook = renderHook((p: EventsProps) => useSessionEvents(p), { initialProps: props });
  return { ...hook, ...handlers, sessionActiveRef, props };
}

function captureBroadcasts() {
  const details: Array<{ voiceState: string; audioLevel: number }> = [];
  const listener = (event: Event) => {
    details.push((event as CustomEvent<{ voiceState: string; audioLevel: number }>).detail);
  };
  window.addEventListener('myrm-voice-state-update', listener);
  return { details, stop: () => window.removeEventListener('myrm-voice-state-update', listener) };
}

describe('useSessionEvents', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('toggle starts an idle session and stops a running one', () => {
    const { startSession, stopSession, sessionActiveRef } = setup();

    window.dispatchEvent(new Event('myrm-voice-toggle'));
    expect(startSession).toHaveBeenCalledTimes(1);
    expect(stopSession).not.toHaveBeenCalled();

    sessionActiveRef.current = true;
    window.dispatchEvent(new Event('myrm-voice-toggle'));
    expect(stopSession).toHaveBeenCalledTimes(1);
    expect(startSession).toHaveBeenCalledTimes(1);
  });

  it('interrupt and replay events reach the session handlers', () => {
    const { interruptTTS, replayLastTTS } = setup();

    window.dispatchEvent(new Event('myrm-voice-interrupt'));
    window.dispatchEvent(new Event('myrm-voice-replay'));

    expect(interruptTTS).toHaveBeenCalledTimes(1);
    expect(replayLastTTS).toHaveBeenCalledTimes(1);
  });

  it('stops listening to window events after unmount', () => {
    const { unmount, startSession, interruptTTS, replayLastTTS } = setup();

    unmount();
    window.dispatchEvent(new Event('myrm-voice-toggle'));
    window.dispatchEvent(new Event('myrm-voice-interrupt'));
    window.dispatchEvent(new Event('myrm-voice-replay'));

    expect(startSession).not.toHaveBeenCalled();
    expect(interruptTTS).not.toHaveBeenCalled();
    expect(replayLastTTS).not.toHaveBeenCalled();
  });

  it.each([
    ['inactive', 'idle'],
    ['listening', 'listening'],
    ['paused', 'listening'],
    ['processing', 'processing'],
    ['speaking', 'speaking'],
  ] as Array<[VoiceSessionState, string]>)('broadcasts session state %s as voice state %s with the audio level', (sessionState, voiceState) => {
    const broadcasts = captureBroadcasts();

    setup({ sessionState, audioLevel: 0.4 });
    broadcasts.stop();

    expect(broadcasts.details).toEqual([{ voiceState, audioLevel: 0.4 }]);
  });

  it('broadcasts again when the audio level changes', () => {
    const { rerender, props } = setup({ sessionState: 'listening', audioLevel: 0.1 });
    const broadcasts = captureBroadcasts();

    rerender({ ...props, audioLevel: 0.7 });
    broadcasts.stop();

    expect(broadcasts.details).toEqual([{ voiceState: 'listening', audioLevel: 0.7 }]);
  });
});
