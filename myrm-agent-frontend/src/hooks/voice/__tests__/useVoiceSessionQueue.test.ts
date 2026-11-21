import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const ttsMock = vi.hoisted(() => ({
  speak: vi.fn(),
  stop: vi.fn(),
}));

const ttsState = vi.hoisted(() => ({ value: 'idle' as string }));

const speechMock = vi.hoisted(() => ({
  startRecording: vi.fn(),
  stopRecording: vi.fn(),
}));

const bridgeMock = vi.hoisted(() => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
  cancelTts: vi.fn(),
}));

const realtimeMock = vi.hoisted(() => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
}));

const geminiMock = vi.hoisted(() => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
}));

const liveNotesMock = vi.hoisted(() => ({
  hook: vi.fn(),
  // Stable identity, like the memoised return of the real hook.
  value: { sessionId: 'live-test', snapshot: null, ingest: vi.fn() },
}));

vi.mock('../useLiveMeetingNotes', () => ({
  useLiveMeetingNotes: (...args: unknown[]) => {
    liveNotesMock.hook(...args);
    return liveNotesMock.value;
  },
}));

vi.mock('../useTTS', () => ({
  useTTS: () => ({
    // speak() flips state to 'speaking' like the real TTS; the idle→next effect
    // only fires once an utterance has finished playing.
    state: ttsState.value,
    speak: (text: string) => {
      ttsState.value = 'speaking';
      ttsMock.speak(text);
    },
    pause: vi.fn(),
    resume: vi.fn(),
    stop: () => {
      ttsState.value = 'idle';
      ttsMock.stop();
    },
    toggle: vi.fn(),
    supported: true,
  }),
}));

let mockSpeechInputOptions: { onTranscript?: (text: string) => void } = {};

vi.mock('../useSpeechInput', () => ({
  useSpeechInput: (options?: { onTranscript?: (text: string) => void }) => {
    if (options) {
      mockSpeechInputOptions = options;
    }
    return {
      state: 'idle',
      elapsed: 0,
      audioLevel: 0,
      interimText: '',
      toggle: vi.fn(),
      startRecording: speechMock.startRecording,
      stopRecording: speechMock.stopRecording,
      onPointerDown: vi.fn(),
      onPointerUp: vi.fn(),
      isSupported: true,
      mode: 'toggle',
    };
  },
}));

vi.mock('../useVoiceAgentBridge', () => ({
  useVoiceAgentBridge: () => ({
    state: 'disconnected',
    connect: bridgeMock.connect,
    disconnect: bridgeMock.disconnect,
    cancelTts: bridgeMock.cancelTts,
    interimText: '',
    agentResponseText: '',
    agentToolName: '',
    audioLevel: 0,
  }),
}));

vi.mock('../useRealtimeVoice', () => ({
  useRealtimeVoice: () => ({
    state: 'idle',
    connect: realtimeMock.connect,
    disconnect: realtimeMock.disconnect,
    interimText: '',
    responseText: '',
  }),
}));

vi.mock('../useGeminiLiveVoice', () => ({
  useGeminiLiveVoice: () => ({
    state: 'idle',
    connect: geminiMock.connect,
    disconnect: geminiMock.disconnect,
    interimText: '',
    responseText: '',
  }),
}));

import { useVoiceSession } from '../useVoiceSession';

describe('useVoiceSession speakResponse queue insertion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ttsState.value = 'idle';
  });

  it('plays immediately when not speaking and no queue flag', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      result.current.startSession();
    });
    act(() => {
      result.current.speakResponse('Hello world.');
    });

    expect(ttsMock.speak).toHaveBeenCalledWith('Hello world.');
  });

  it('defers queued text until the current utterance finishes', () => {
    const { result, rerender } = renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }),
    );

    act(() => {
      result.current.startSession();
    });
    act(() => {
      result.current.speakResponse('Announcement.');
    });
    expect(ttsMock.speak).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.speakResponse('Background task done.', { queue: true });
    });

    // Queue-safe insertion: current utterance keeps playing, no interruption.
    expect(ttsMock.speak).toHaveBeenCalledTimes(1);

    // Simulate the current utterance finishing (idle) → queued segment plays next.
    act(() => {
      ttsState.value = 'idle';
      rerender();
    });

    expect(ttsMock.speak).toHaveBeenCalledTimes(2);
    expect(ttsMock.speak).toHaveBeenLastCalledWith('Background task done.');
  });

  it('replaces the pending queue when the queue flag is not set', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      result.current.startSession();
    });
    act(() => {
      result.current.speakResponse('First.');
      result.current.speakResponse('Second.', { queue: true });
      result.current.speakResponse('Third.');
    });

    // 'First.' started, 'Second.' queued, then non-queued 'Third.' replaced the queue.
    expect(ttsMock.speak).toHaveBeenLastCalledWith('Third.');
  });

  it('ignores speakResponse when the session is inactive', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      result.current.speakResponse('Nobody hears this.');
    });

    expect(ttsMock.speak).not.toHaveBeenCalled();
  });

  it('stops the session and clears the queue', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      result.current.startSession();
      result.current.speakResponse('First.');
      result.current.speakResponse('Second.', { queue: true });
    });
    expect(ttsMock.speak).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.stopSession();
    });
    act(() => {
      result.current.speakResponse('After stop.', { queue: true });
    });

    expect(ttsMock.speak).toHaveBeenCalledTimes(1);
  });

  it('delegates to WebSocket connect for agent_bridge mode', () => {
    const { result } = renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'agent_bridge', fullDuplex: true, chatId: 'chat-1' }),
    );

    act(() => {
      result.current.startSession();
    });

    expect(bridgeMock.connect).toHaveBeenCalledOnce();
    expect(speechMock.startRecording).not.toHaveBeenCalled();
  });

  it('delegates to Realtime connect for openai_realtime mode', () => {
    const { result } = renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'openai_realtime', fullDuplex: true, chatId: 'chat-1' }),
    );

    act(() => {
      result.current.startSession();
    });

    expect(realtimeMock.connect).toHaveBeenCalledOnce();
  });

  it('delegates to Gemini Live connect for gemini_live mode', () => {
    const { result } = renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'gemini_live', fullDuplex: true, chatId: 'chat-1' }),
    );

    act(() => {
      result.current.startSession();
    });

    expect(geminiMock.connect).toHaveBeenCalledOnce();
  });

  it('speaks the last response again when the replay event arrives (F13 DoD)', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      result.current.startSession();
      result.current.speakResponse('Important instruction.');
    });
    expect(ttsMock.speak).toHaveBeenLastCalledWith('Important instruction.');

    act(() => {
      window.dispatchEvent(new Event('myrm-voice-replay'));
    });
    expect(ttsMock.speak).toHaveBeenCalledTimes(2);
    expect(ttsMock.speak).toHaveBeenLastCalledWith('Important instruction.');
  });

  it('replays the whole last response from its first sentence, not just the sentence spoken last', () => {
    const { result, rerender } = renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }),
    );
    act(() => {
      result.current.startSession();
      result.current.speakResponse('First sentence. Second sentence.');
    });
    for (let sentence = 0; sentence < 2; sentence += 1) {
      act(() => {
        ttsState.value = 'idle';
        rerender();
      });
    }
    expect(ttsMock.speak.mock.calls.map(([text]) => text)).toEqual(['First sentence.', 'Second sentence.']);

    act(() => {
      window.dispatchEvent(new Event('myrm-voice-replay'));
    });

    expect(ttsMock.speak).toHaveBeenCalledTimes(3);
    expect(ttsMock.speak).toHaveBeenLastCalledWith('First sentence.');
  });

  it('replays nothing when nothing was spoken yet', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));
    act(() => {
      result.current.startSession();
    });

    act(() => {
      window.dispatchEvent(new Event('myrm-voice-replay'));
    });

    expect(ttsMock.speak).not.toHaveBeenCalled();
  });

  it('stops speech on the interrupt event only while the session is speaking', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      window.dispatchEvent(new Event('myrm-voice-interrupt'));
    });
    expect(ttsMock.stop).not.toHaveBeenCalled();

    act(() => {
      result.current.startSession();
      result.current.speakResponse('A long answer.');
    });
    act(() => {
      window.dispatchEvent(new Event('myrm-voice-interrupt'));
    });

    expect(ttsMock.stop).toHaveBeenCalledOnce();
  });

  it('starts and stops the session once per toggle event', () => {
    const { result } = renderHook(() => useVoiceSession({ enabled: true, mode: 'audio_only', fullDuplex: true }));

    act(() => {
      window.dispatchEvent(new Event('myrm-voice-toggle'));
    });
    expect(speechMock.startRecording).toHaveBeenCalledOnce();
    expect(result.current.isActive).toBe(true);

    act(() => {
      window.dispatchEvent(new Event('myrm-voice-toggle'));
    });
    expect(result.current.isActive).toBe(false);
  });

  it('formats context prioritizing selectedText over extractedText when voice-ptt-context is received', async () => {
    const mockOnSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceSession({
        enabled: true,
        mode: 'audio_only',
        fullDuplex: true,
        autoSend: true,
        onSendMessage: mockOnSendMessage,
      }),
    );

    act(() => {
      result.current.startSession();
    });

    // Simulate voice-ptt-context event with selectedText
    act(() => {
      window.dispatchEvent(
        new CustomEvent('voice-ptt-context', {
          detail: {
            windowTitle: 'VS Code',
            extractedText: 'entire document text here',
            selectedText: 'function calculate() { return 42; }',
            screenshot: '',
            timestamp: Date.now(),
          },
        }),
      );
    });

    // Trigger transcript handler directly via mock captured speech input options
    await act(async () => {
      await mockSpeechInputOptions.onTranscript?.('explain this code');
    });

    expect(mockOnSendMessage).toHaveBeenCalledWith(
      expect.stringContaining('[Selected Text: function calculate() { return 42; }]'),
      undefined,
    );
    expect(mockOnSendMessage).toHaveBeenCalledWith(
      expect.not.stringContaining('[Screen Text: entire document text here]'),
      undefined,
    );
    expect(mockOnSendMessage).toHaveBeenCalledWith(expect.stringContaining('[Active Window: VS Code]'), undefined);
  });

  it('sends the push-to-talk screenshot with the message as its only vision frame', async () => {
    const mockOnSendMessage = vi.fn();
    const { result } = renderHook(() =>
      useVoiceSession({
        enabled: true,
        mode: 'audio_only',
        fullDuplex: true,
        autoSend: true,
        onSendMessage: mockOnSendMessage,
      }),
    );

    act(() => {
      result.current.startSession();
    });

    const timestamp = Date.now();
    act(() => {
      window.dispatchEvent(
        new CustomEvent('voice-ptt-context', {
          detail: {
            windowTitle: 'Safari',
            extractedText: '',
            selectedText: '',
            screenshot: 'SCREENSHOT_BASE64',
            timestamp,
          },
        }),
      );
    });

    await act(async () => {
      await mockSpeechInputOptions.onTranscript?.('what is on my screen');
    });

    expect(mockOnSendMessage).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('what is on my screen'), [
      'SCREENSHOT_BASE64',
    ]);
  });
});

describe('useVoiceSession live meeting notes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ttsState.value = 'idle';
  });

  it('keys the live notes to the chat and to the agent whose vault receives the minutes', () => {
    renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'agent_bridge', fullDuplex: true, chatId: 'chat-1', agentId: 'agent-1' }),
    );

    expect(liveNotesMock.hook).toHaveBeenLastCalledWith('chat-1', 'agent-1', false);
  });

  it('tells the live notes when the session is running, which is what ends a meeting', () => {
    const { result } = renderHook(() =>
      useVoiceSession({ enabled: true, mode: 'agent_bridge', fullDuplex: true, chatId: 'chat-1' }),
    );
    expect(liveNotesMock.hook).toHaveBeenLastCalledWith('chat-1', undefined, false);

    act(() => {
      result.current.startSession();
    });
    expect(liveNotesMock.hook).toHaveBeenLastCalledWith('chat-1', undefined, true);

    act(() => {
      result.current.stopSession();
    });
    expect(liveNotesMock.hook).toHaveBeenLastCalledWith('chat-1', undefined, false);
  });
});
