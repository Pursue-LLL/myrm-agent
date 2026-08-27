import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSpeechInput } from '../useSpeechInput';
import { useVoiceAgentBridge } from '../useVoiceAgentBridge';
import { toast } from '@/lib/utils/toast';

const mockIsLocalBackendReadyCached = vi.hoisted(() => vi.fn(() => true));
const mockEnsureLocalBackendReady = vi.hoisted(() => vi.fn(async () => true));

vi.mock('@/lib/backend-health', () => ({
  isLocalBackendReadyCached: () => mockIsLocalBackendReadyCached(),
  ensureLocalBackendReady: () => mockEnsureLocalBackendReady(),
}));

const voiceTranslationsMap: Record<string, string> = {
  hostNotReadyTitle: 'Backend service is not ready',
  hostNotReadyDesc: 'The backend service is connecting or offline.',
  localSttUnavailableTitle: 'Local Whisper STT is not available',
  localSttUnavailableDesc: 'Local STT component is not installed.',
};
const stableVoiceT = (key: string) => voiceTranslationsMap[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableVoiceT,
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
  getWsUrl: (path: string) => `ws://localhost:8080${path}`,
  ApiError: class ApiError extends Error {
    code: number;
    constructor(message: string, code: number) {
      super(message);
      this.code = code;
    }
  },
}));

describe('VoiceModeHostReadyGate in useSpeechInput', () => {
  let mockGetUserMedia: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLocalBackendReadyCached.mockReturnValue(true);

    mockGetUserMedia = vi.fn().mockResolvedValue({
      getTracks: () => [{ stop: vi.fn() }],
    });

    Object.defineProperty(globalThis.navigator, 'mediaDevices', {
      value: { getUserMedia: mockGetUserMedia },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('blocks startRecording when host is not ready and triggers toast & background probe', async () => {
    mockIsLocalBackendReadyCached.mockReturnValue(false);

    const onTranscript = vi.fn();
    const onError = vi.fn();

    const { result } = renderHook(() =>
      useSpeechInput({
        onTranscript,
        onError,
      }),
    );

    await act(async () => {
      result.current.toggle();
    });

    expect(mockGetUserMedia).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(
      'Backend service is not ready',
      expect.objectContaining({
        description: 'The backend service is connecting or offline.',
      }),
    );
    expect(mockEnsureLocalBackendReady).toHaveBeenCalledTimes(1);
    expect(result.current.state).toBe('idle');
  });

  it('blocks global voice-ptt-start event when host is not ready', async () => {
    mockIsLocalBackendReadyCached.mockReturnValue(false);

    const onTranscript = vi.fn();
    const onError = vi.fn();

    const { result } = renderHook(() =>
      useSpeechInput({
        onTranscript,
        onError,
        mode: 'push-to-talk',
      }),
    );

    await act(async () => {
      window.dispatchEvent(new CustomEvent('voice-ptt-start'));
    });

    expect(mockGetUserMedia).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Backend service is not ready', expect.anything());
    expect(result.current.state).toBe('idle');
  });

  it('allows startRecording when host is ready', async () => {
    mockIsLocalBackendReadyCached.mockReturnValue(true);

    const onTranscript = vi.fn();
    const onError = vi.fn();

    const { result } = renderHook(() =>
      useSpeechInput({
        onTranscript,
        onError,
      }),
    );

    await act(async () => {
      result.current.toggle();
    });

    expect(mockGetUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(toast.error).not.toHaveBeenCalled();
    expect(result.current.state).toBe('recording');
  });
});

describe('VoiceModeHostReadyGate in useVoiceAgentBridge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLocalBackendReadyCached.mockReturnValue(true);
  });

  it('blocks connect() when host is not ready, transitions to error, and triggers background probe', () => {
    mockIsLocalBackendReadyCached.mockReturnValue(false);

    const onError = vi.fn();

    const { result } = renderHook(() =>
      useVoiceAgentBridge({
        enabled: true,
        onError,
      }),
    );

    act(() => {
      result.current.connect();
    });

    expect(onError).toHaveBeenCalledWith('Backend service is not ready');
    expect(result.current.state).toBe('error');
    expect(mockEnsureLocalBackendReady).toHaveBeenCalledTimes(1);
  });
});
