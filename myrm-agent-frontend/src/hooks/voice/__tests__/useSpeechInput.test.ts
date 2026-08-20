import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mockToastError = vi.fn();
const mockOnTranscript = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    getWsUrl: (path: string) => `ws://127.0.0.1:8080${path}`,
  };
});

vi.mock('@/lib/mobileRemote', () => ({
  getMobilePairToken: () => null,
}));

type WsHandler = {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  onclose: ((event: { code: number }) => void) | null;
};

class MockWebSocket {
  static OPEN = 1;
  static lastInstance: WsHandler | null = null;
  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;

  constructor(_url: string) {
    MockWebSocket.lastInstance = this;
    queueMicrotask(() => this.onopen?.());
  }

  send = vi.fn();
  close = vi.fn();
}

class MockMediaRecorder {
  static isTypeSupported = () => true;
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: MediaStream, _options?: MediaRecorderOptions) {}

  start = vi.fn(() => {
    this.state = 'recording';
  });

  stop = vi.fn(() => {
    this.state = 'inactive';
    this.onstop?.();
  });
}

function mockAudioStream(): MediaStream {
  return {
    getTracks: () => [{ stop: vi.fn() }],
  } as unknown as MediaStream;
}

describe('useSpeechInput local STT unavailable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockWebSocket.lastInstance = null;
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket);
    vi.stubGlobal('MediaRecorder', MockMediaRecorder as unknown as typeof MediaRecorder);
    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => mockAudioStream()),
      },
    });
    Object.defineProperty(globalThis, 'AudioContext', {
      configurable: true,
      writable: true,
      value: undefined,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows bilingual toast keys when WS STT reports local-stt missing', async () => {
    const { useSpeechInput } = await import('../useSpeechInput');
    const { result } = renderHook(() => useSpeechInput({ onTranscript: mockOnTranscript, minDuration: 0 }));

    await act(async () => {
      await result.current.startRecording();
    });

    await act(async () => {
      MockWebSocket.lastInstance?.onmessage?.({
        data: JSON.stringify({
          type: 'error',
          message: 'Install local-stt (uv sync --extra local-stt)',
        }),
      });
    });

    expect(mockToastError).toHaveBeenCalledWith('localSttUnavailableTitle', {
      description: 'localSttUnavailableDesc',
    });
  });
});
