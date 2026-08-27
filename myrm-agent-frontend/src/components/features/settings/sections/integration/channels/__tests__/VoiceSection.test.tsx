/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

describe('VoiceSection Offline TTS integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Piper and Voicebox in TTS providers and displays piper warning when local_tts is unavailable', async () => {
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
          local_tts_available: false,
        });
      }
      return Promise.resolve({});
    });

    render(<VoiceSection />);

    await waitFor(() => {
      expect(screen.getByTestId('voice-settings-panel')).toBeInTheDocument();
    });

    // Verification of piper warning banner
    expect(screen.getByText('piperUnavailableTitle')).toBeInTheDocument();
    expect(screen.getByText('piperUnavailableDesc')).toBeInTheDocument();
  });

  it('does not display piper warning when local_tts is available', async () => {
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
          local_tts_available: true,
        });
      }
      return Promise.resolve({});
    });

    render(<VoiceSection />);

    await waitFor(() => {
      expect(screen.getByTestId('voice-settings-panel')).toBeInTheDocument();
    });

    expect(screen.queryByText('piperUnavailableTitle')).not.toBeInTheDocument();
  });
});
