/**
 * [INPUT]
 * - services/config/types::VoiceConfigValue (POS: voice config REST value shape)
 *
 * [OUTPUT]
 * - TtsProviderId, TtsModelOption, StoredVoice, StoredChoices
 * - TTS_PROVIDER_OPTIONS, TTS_MODEL_OPTIONS, TTS_VOICE_OPTIONS
 * - isTtsProvider, isTtsSelected, readStoredChoices
 *
 * [POS]
 * What the TTS settings card offers (providers, models, voices) and how the shared `voice` config maps onto those
 * choices. Nothing is chosen until the user chooses it: no provider, model or voice is filled in on their behalf. Pure
 * data and functions, so the card and the agent readiness check share one definition of "chosen".
 */

import type { VoiceConfigValue } from '@/services/config/types';

export type TtsProviderId = 'openai' | 'elevenlabs' | 'volcengine';

/** What the server holds under `voice`; every field is optional because nothing may be saved yet. */
export type StoredVoice = Partial<VoiceConfigValue>;

export interface TtsModelOption {
  value: string;
  label: string;
  description: string;
}

export const TTS_PROVIDER_OPTIONS: TtsModelOption[] = [
  { value: 'openai', label: 'OpenAI TTS', description: 'tts-1 / gpt-4o-mini-tts' },
  { value: 'elevenlabs', label: 'ElevenLabs', description: 'Turbo v2.5 / Multilingual v2' },
  { value: 'volcengine', label: 'Volcengine Speech', description: 'Seed-Audio / Doubao-TTS' },
];

export const TTS_MODEL_OPTIONS: Record<TtsProviderId, TtsModelOption[]> = {
  openai: [
    { value: 'tts-1', label: 'TTS 1', description: 'Fast' },
    { value: 'tts-1-hd', label: 'TTS 1 HD', description: 'Higher fidelity' },
    { value: 'gpt-4o-mini-tts', label: 'GPT-4o mini TTS', description: 'Steerable' },
  ],
  elevenlabs: [
    { value: 'eleven_turbo_v2_5', label: 'Turbo v2.5', description: 'Low latency' },
    { value: 'eleven_multilingual_v2', label: 'Multilingual v2', description: '30+ languages' },
    { value: 'eleven_flash_v2_5', label: 'Flash v2.5', description: 'Fastest' },
  ],
  volcengine: [
    { value: 'seed-audio-1.0', label: 'Seed-Audio 1.0', description: 'Generative · style-aware' },
    { value: 'doubao-tts', label: 'Doubao-TTS', description: 'Low latency codec' },
  ],
};

export const TTS_VOICE_OPTIONS: Record<TtsProviderId, TtsModelOption[]> = {
  openai: [
    { value: 'alloy', label: 'Alloy', description: '' },
    { value: 'echo', label: 'Echo', description: '' },
    { value: 'fable', label: 'Fable', description: '' },
    { value: 'onyx', label: 'Onyx', description: '' },
    { value: 'nova', label: 'Nova', description: '' },
    { value: 'shimmer', label: 'Shimmer', description: '' },
  ],
  elevenlabs: [
    { value: '21m00Tcm4TlvDq8ikWAM', label: 'Rachel', description: '' },
    { value: 'AZnzlk1XvdvUeBnXmlld', label: 'Domi', description: '' },
    { value: 'EXAVITQu4vr4xnSDxMaL', label: 'Sarah', description: '' },
    { value: 'TxGEqnHWrfWFTfGW9XjX', label: 'Josh', description: '' },
  ],
  volcengine: [
    { value: 'zh_female_vv_uranus_bigtts', label: 'Uranus · 中文女声', description: '' },
    { value: 'zh_male_rough_mars_bigtts', label: 'Mars · 中文男声', description: '' },
    { value: 'en_female_emily_mars_bigtts', label: 'Emily · English', description: '' },
  ],
};

export const isTtsProvider = (id: string | undefined): id is TtsProviderId =>
  TTS_PROVIDER_OPTIONS.some((option) => option.value === id);

/**
 * The server's own test for handing the agent the speech tool: a provider the engine calls, with a model and a voice.
 * A provider the channel voice settings save (edge, piper, ...) fails it, because the tool cannot synthesize with it.
 */
export const isTtsSelected = (
  provider: string | undefined,
  model: string | undefined,
  voice: string | undefined,
): boolean => isTtsProvider(provider) && Boolean(model?.trim()) && Boolean(voice?.trim());

export interface StoredChoices {
  /** As stored, empty when nothing is: a provider the card does not offer is kept so the card can ask for a new one. */
  provider: string;
  model: string;
  voice: string;
  keySaved: boolean;
}

/**
 * The card's choices as the stored settings describe them. The channel voice settings share these fields and also
 * save providers this card does not offer (edge, piper, ...); their model, voice and key mean nothing here, so for such
 * a provider only the provider itself is reported.
 */
export function readStoredChoices(value: StoredVoice): StoredChoices {
  const provider = value.ttsProvider?.trim() ?? '';
  const own: StoredVoice = isTtsProvider(provider) ? value : {};
  return {
    provider,
    model: own.ttsModel?.trim() ?? '',
    voice: own.ttsVoice?.trim() ?? '',
    keySaved: Boolean(own.ttsApiKey?.trim()),
  };
}
