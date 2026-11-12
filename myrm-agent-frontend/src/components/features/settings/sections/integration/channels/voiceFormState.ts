import { apiRequest } from '@/lib/api';

export interface VoiceFormState {
  sttEnabled: boolean;
  sttProvider: string;
  sttApiKey: string;
  sttModel: string;
  sttLanguage: string;
  sttLocalModel: string;
  sttLocalDevice: string;
  sttLocalComputeType: string;
  sttBaseUrl: string;
  ttsMode: string;
  ttsProvider: string;
  ttsApiKey: string;
  ttsBaseUrl: string;
  ttsVoice: string;
  ttsSpeed: number;
  ttsPitch: number;
  ttsMaxLength: number;
  ttsSummaryEnabled: boolean;
  ttsSummaryThreshold: number;
  ttsSummaryModel: string;
  geminiLiveModel: string;
}

/** Changes part of the voice form; every change is saved after a short pause. */
export type UpdateVoiceForm = (patch: Partial<VoiceFormState>) => void;

export const DEFAULT_VOICE_FORM: VoiceFormState = {
  sttEnabled: false,
  sttProvider: 'openai',
  sttApiKey: '',
  sttModel: 'whisper-1',
  sttLanguage: '',
  sttLocalModel: 'base',
  sttLocalDevice: 'auto',
  sttLocalComputeType: 'auto',
  sttBaseUrl: '',
  ttsMode: 'off',
  ttsProvider: 'edge',
  ttsApiKey: '',
  ttsBaseUrl: '',
  ttsVoice: '',
  ttsSpeed: 1.0,
  ttsPitch: 0,
  ttsMaxLength: 4000,
  ttsSummaryEnabled: true,
  ttsSummaryThreshold: 1500,
  ttsSummaryModel: '',
  geminiLiveModel: 'gemini-2.5-flash-preview-native-audio-dialog',
};

/**
 * Rejects when the saved settings cannot be read. Answering with the defaults instead would show them as the user's
 * settings, and the next edit would save them over whatever is really stored. Nothing saved yet is not a failure: the
 * server answers that with an empty value, which fills up with the defaults. The read is silent because the section
 * shows the failure itself, with a retry that reaches the section; the global notice's retry would not.
 */
export async function loadVoiceConfig(): Promise<VoiceFormState> {
  const record = await apiRequest<{ value: VoiceFormState }>('/config/voice', { silent: true });
  return { ...DEFAULT_VOICE_FORM, ...record.value };
}

export async function saveVoiceConfig(state: VoiceFormState): Promise<void> {
  await apiRequest('/config/voice', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value: state, device_id: 'web' }),
  });
}
