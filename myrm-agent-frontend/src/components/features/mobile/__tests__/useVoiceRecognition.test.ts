/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useVoiceRecognition } from '../useVoiceRecognition';

interface MockSpeechInstance {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: { results: Array<Array<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

describe('useVoiceRecognition', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete (window as unknown as { SpeechRecognition?: unknown }).SpeechRecognition;
    delete (window as unknown as { webkitSpeechRecognition?: unknown }).webkitSpeechRecognition;
  });

  it('calls onUnsupported if SpeechRecognition is not available on window', () => {
    const onUnsupported = vi.fn();
    const { result } = renderHook(() => useVoiceRecognition({ onUnsupported }));

    expect(result.current.isListening).toBe(false);

    act(() => {
      result.current.toggleRecognition();
    });

    expect(onUnsupported).toHaveBeenCalledTimes(1);
    expect(result.current.isListening).toBe(false);
  });

  it('starts recognition and handles transcript chunks', () => {
    const onTranscriptChunk = vi.fn();
    let currentInstance: MockSpeechInstance | null = null;

    const createMockSpeechRecognition = (): MockSpeechInstance => {
      const instance: MockSpeechInstance = {
        continuous: false,
        interimResults: false,
        lang: '',
        onresult: null,
        onerror: null,
        onend: null,
        start: () => {},
        stop() {
          instance.onend?.();
        },
      };
      currentInstance = instance;
      return instance;
    };

    (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = function (this: unknown) {
      return createMockSpeechRecognition();
    };

    const { result } = renderHook(() => useVoiceRecognition({ onTranscriptChunk }));

    act(() => {
      result.current.toggleRecognition();
    });

    expect(result.current.isListening).toBe(true);
    expect(currentInstance).not.toBeNull();

    // Simulate incoming speech transcript
    act(() => {
      currentInstance?.onresult?.({
        results: [[{ transcript: 'Hello ' }], [{ transcript: 'World' }]],
      });
    });

    expect(onTranscriptChunk).toHaveBeenCalledWith('Hello World');
    expect(result.current.transcript).toBe('Hello World');

    // Reset transcript
    act(() => {
      result.current.resetTranscript();
    });
    expect(result.current.transcript).toBe('');

    // Toggle off
    act(() => {
      result.current.toggleRecognition();
    });
    expect(result.current.isListening).toBe(false);
  });

  it('stops recognition via stopRecognition', () => {
    class MockSpeechRecognition implements MockSpeechInstance {
      continuous = false;
      interimResults = false;
      lang = '';
      onresult = null;
      onerror = null;
      onend = null;
      start = vi.fn();
      stop = vi.fn();
    }

    (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition = MockSpeechRecognition;

    const { result } = renderHook(() => useVoiceRecognition());

    act(() => {
      result.current.toggleRecognition();
    });
    expect(result.current.isListening).toBe(true);

    act(() => {
      result.current.stopRecognition();
    });
    expect(result.current.isListening).toBe(false);
  });
});
