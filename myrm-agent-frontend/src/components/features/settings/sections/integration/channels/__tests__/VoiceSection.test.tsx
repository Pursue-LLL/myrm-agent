/** @vitest-environment jsdom */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { VOICE_SETTING_KEYS, voiceDeviceSettings } from '@/hooks/voice/voiceDeviceSettings';
import VoiceSection from '../VoiceSection';

const apiRequestMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({
  apiRequest: apiRequestMock,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// The shared failure view probes the backend on its own; only its retry hand-off matters here.
vi.mock('@/components/features/app-shell/config-load-error', () => ({
  ConfigLoadError: ({ onRetry }: { onRetry: () => void }) => (
    <button type="button" data-testid="config-load-error" onClick={onRetry}>
      retry
    </button>
  ),
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

function mockVoiceApi({ localTtsAvailable }: { localTtsAvailable: boolean }): void {
  apiRequestMock.mockImplementation((url: string) => {
    if (url === '/config/voice') {
      return Promise.resolve({
        value: {
          sttEnabled: true,
          sttProvider: 'openai',
          ttsMode: 'always',
          ttsProvider: 'piper',
          ttsVoice: 'en_US-lessac-medium',
        },
      });
    }
    if (url === '/health/info') {
      return Promise.resolve({
        edge_tts_available: true,
        local_stt_available: true,
        local_tts_available: localTtsAvailable,
      });
    }
    return Promise.resolve({});
  });
}

async function renderLoadedSection(): Promise<void> {
  // The saved config and the server's health info arrive after the first paint; letting them land inside act keeps
  // every update the section makes on its own accounted for.
  await act(async () => {
    render(<VoiceSection />);
  });
  await waitFor(() => {
    expect(screen.getByTestId('voice-settings-panel')).toBeInTheDocument();
  });
}

describe('VoiceSection Offline TTS integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Piper and Voicebox in TTS providers and displays piper warning when local_tts is unavailable', async () => {
    mockVoiceApi({ localTtsAvailable: false });

    await renderLoadedSection();

    // Verification of piper warning banner
    expect(screen.getByText('piperUnavailableTitle')).toBeInTheDocument();
    expect(screen.getByText('piperUnavailableDesc')).toBeInTheDocument();
  });

  it('does not display piper warning when local_tts is available', async () => {
    mockVoiceApi({ localTtsAvailable: true });

    await renderLoadedSection();

    expect(screen.queryByText('piperUnavailableTitle')).not.toBeInTheDocument();
  });
});

describe('VoiceSection voice session mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockVoiceApi({ localTtsAvailable: true });
  });

  afterEach(() => {
    // Unmount first: forgetting the mode while the section is mounted would update it outside act.
    cleanup();
    vi.unstubAllGlobals();
    voiceDeviceSettings.remove(VOICE_SETTING_KEYS.mode);
    localStorage.clear();
  });

  const modePicker = () => within(screen.getByText('voiceMode').parentElement as HTMLElement).getByRole('combobox');

  async function pickMode(label: string): Promise<void> {
    fireEvent.click(modePicker());
    fireEvent.click(await screen.findByRole('option', { name: label }));
  }

  function refuseStorage(): void {
    const refuse = () => {
      throw new DOMException('blocked', 'SecurityError');
    };
    vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse });
  }

  it('opens on the saved mode', async () => {
    localStorage.setItem(VOICE_SETTING_KEYS.mode, 'gemini_live');

    await renderLoadedSection();

    expect(modePicker()).toHaveTextContent('voiceModeGeminiLive');
  });

  it('opens on audio only when nothing is saved', async () => {
    await renderLoadedSection();

    expect(modePicker()).toHaveTextContent('voiceModeAudioOnly');
  });

  it('saves the chosen mode and tells the voice button at once', async () => {
    await renderLoadedSection();
    const heard = vi.fn();
    const stopListening = voiceDeviceSettings.subscribe(heard);

    await pickMode('voiceModeAgentBridge');

    expect(localStorage.getItem(VOICE_SETTING_KEYS.mode)).toBe('agent_bridge');
    expect(modePicker()).toHaveTextContent('voiceModeAgentBridge');
    expect(heard).toHaveBeenCalledTimes(1);
    stopListening();
  });

  it('follows a mode chosen somewhere else without reloading', async () => {
    await renderLoadedSection();

    act(() => {
      voiceDeviceSettings.write(VOICE_SETTING_KEYS.mode, 'openai_realtime');
    });

    expect(modePicker()).toHaveTextContent('voiceModeRealtime');
  });

  it('offers the voice and the model pickers only in the modes that use them', async () => {
    await renderLoadedSection();
    expect(screen.queryByText('realtimeVoice')).not.toBeInTheDocument();
    expect(screen.queryByText('geminiLiveModel')).not.toBeInTheDocument();

    await pickMode('voiceModeRealtime');
    expect(screen.getByText('realtimeVoice')).toBeInTheDocument();
    expect(screen.queryByText('geminiLiveModel')).not.toBeInTheDocument();

    await pickMode('voiceModeGeminiLive');
    expect(screen.queryByText('realtimeVoice')).not.toBeInTheDocument();
    expect(screen.getByText('geminiLiveModel')).toBeInTheDocument();
  });

  it('opens on audio only instead of crashing when the browser refuses storage', async () => {
    refuseStorage();

    await renderLoadedSection();

    expect(modePicker()).toHaveTextContent('voiceModeAudioOnly');
  });

  it('keeps the chosen mode for the page when the browser refuses to store it', async () => {
    refuseStorage();
    await renderLoadedSection();

    await pickMode('voiceModeGeminiLive');

    expect(modePicker()).toHaveTextContent('voiceModeGeminiLive');
    // What the chat's voice button reads, so the choice takes effect there too.
    expect(voiceDeviceSettings.read(VOICE_SETTING_KEYS.mode)).toBe('gemini_live');
  });
});

interface VoiceRequestInit {
  method?: string;
  body?: string;
  silent?: boolean;
}
type RecordedCall = [url: string, init?: VoiceRequestInit];
type ConfigReadAnswer = Error | { value: Record<string, unknown>; unreadable?: boolean };

const SAVED_VOICE = {
  sttEnabled: true,
  sttProvider: 'openai',
  ttsMode: 'always',
  ttsProvider: 'piper',
  ttsVoice: 'en_US-lessac-medium',
};

/** Answers each read of the saved settings in turn (the last answer repeats); an Error is a failed read. */
function mockConfigReads(...answers: ConfigReadAnswer[]): void {
  let reads = 0;
  apiRequestMock.mockImplementation((url: string, init?: VoiceRequestInit) => {
    if (url === '/config/voice' && init?.method === 'PUT') {
      return Promise.resolve({});
    }
    if (url === '/config/voice') {
      const answer = answers[Math.min(reads, answers.length - 1)];
      reads += 1;
      return answer instanceof Error ? Promise.reject(answer) : Promise.resolve(answer);
    }
    if (url === '/health/info') {
      return Promise.resolve({ edge_tts_available: true, local_stt_available: true, local_tts_available: true });
    }
    return Promise.resolve({});
  });
}

const voiceCalls = (): RecordedCall[] =>
  (apiRequestMock.mock.calls as RecordedCall[]).filter(([url]) => url === '/config/voice');
const configReads = (): number => voiceCalls().filter(([, init]) => init?.method !== 'PUT').length;
const savedBodies = (): Array<{ value: Record<string, unknown> }> =>
  voiceCalls()
    .filter(([, init]) => init?.method === 'PUT')
    .map(([, init]) => JSON.parse(init?.body ?? '{}'));

describe('VoiceSection when the saved settings cannot be read', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  async function renderSection(): Promise<void> {
    await act(async () => {
      render(<VoiceSection />);
    });
  }

  async function retry(): Promise<void> {
    const button = await screen.findByTestId('config-load-error');
    await act(async () => {
      fireEvent.click(button);
    });
  }

  it('offers a retry instead of the form, and saves nothing', async () => {
    mockConfigReads(new Error('backend unreachable'));

    await renderSection();

    expect(await screen.findByTestId('config-load-error')).toBeInTheDocument();
    expect(screen.queryByTestId('voice-settings-panel')).not.toBeInTheDocument();
    expect(savedBodies()).toEqual([]);
  });

  it('asks for the saved settings silently, so a failed read is shown once, by the section', async () => {
    mockConfigReads(new Error('backend unreachable'), { value: SAVED_VOICE });
    await renderSection();
    await retry();
    await screen.findByTestId('voice-settings-panel');

    // The global failure notice would add a second "retry" that cannot reach the section.
    expect(voiceCalls().map(([, init]) => init)).toEqual([{ silent: true }, { silent: true }]);
  });

  it('keeps offering the retry while the read keeps failing', async () => {
    mockConfigReads(new Error('backend unreachable'), new Error('backend unreachable'), { value: SAVED_VOICE });
    await renderSection();

    await retry();
    expect(await screen.findByTestId('config-load-error')).toBeInTheDocument();
    expect(screen.queryByTestId('voice-settings-panel')).not.toBeInTheDocument();

    await retry();
    expect(await screen.findByTestId('voice-settings-panel')).toBeInTheDocument();
    expect(configReads()).toBe(3);
  });

  it('keeps the saved settings in what the next edit saves', async () => {
    mockConfigReads(new Error('backend unreachable'), { value: SAVED_VOICE });
    await renderSection();
    await retry();
    await screen.findByTestId('voice-settings-panel');

    fireEvent.click(within(screen.getByText('sttEnabled').parentElement as HTMLElement).getByRole('switch'));

    await waitFor(() => expect(savedBodies()).toHaveLength(1), { timeout: 3000 });
    // The defaults would say edge / off / no voice; every saved field the user did not touch has to survive.
    expect(savedBodies()[0].value).toMatchObject({
      sttEnabled: false,
      ttsMode: 'always',
      ttsProvider: 'piper',
      ttsVoice: 'en_US-lessac-medium',
    });
  });

  it.each([
    ['nothing was saved yet', { value: {} }],
    ['the saved settings cannot be decrypted', { value: {}, unreadable: true }],
  ])('opens the form on the defaults when %s', async (_case, record) => {
    mockConfigReads(record);

    await renderSection();

    expect(await screen.findByTestId('voice-settings-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('config-load-error')).not.toBeInTheDocument();
  });
});
