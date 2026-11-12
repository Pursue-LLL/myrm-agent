/**
 * [INPUT]
 * - services/config/types::VoiceConfigValue (POS: voice config REST value shape)
 *
 * [OUTPUT]
 * - TtsProviderId, TtsModelOption, StoredVoice, StoredChoices
 * - TTS_PROVIDER_OPTIONS, TTS_MODEL_OPTIONS, TTS_VOICE_OPTIONS
 * - DEFAULT_PROVIDER, DEFAULT_MODEL, DEFAULT_VOICE
 * - readStoredChoices
 *
 * [POS]
 * What the TTS settings card offers (providers, models, voices) and how the shared `voice` config maps onto those
 * choices. Pure data and functions, so the card keeps only its state and layout.
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
    { value: 'zh_female_vv_uranus_bigtts', label: 'Uranus · 中文女声', description: 'Default' },
    { value: 'zh_male_rough_mars_bigtts', label: 'Mars · 中文男声', description: '' },
    { value: 'en_female_emily_mars_bigtts', label: 'Emily · English', description: '' },
  ],
};

export const DEFAULT_PROVIDER: TtsProviderId = 'openai';
export const DEFAULT_MODEL = 'tts-1';
export const DEFAULT_VOICE = 'alloy';

const isTtsProvider = (id: string | undefined): id is TtsProviderId =>
  TTS_PROVIDER_OPTIONS.some((option) => option.value === id);

export interface StoredChoices {
  provider: TtsProviderId;
  model: string;
  voice: string;
  keySaved: boolean;
}

/**
 * The card's choices as the stored settings describe them. The channel voice settings share these fields and also
 * save providers this card does not offer (edge, piper, ...); their model, voice and key mean nothing here, so such
 * settings give the card's defaults instead of a combination it cannot show.
 */
export function readStoredChoices(value: StoredVoice): StoredChoices {
  const saved = value.ttsProvider;
  const provider = isTtsProvider(saved) ? saved : DEFAULT_PROVIDER;
  const own: StoredVoice = saved && provider !== saved ? {} : value;
  const savedModel = own.ttsModel || DEFAULT_MODEL;
  return {
    provider,
    // 'tts-1' is OpenAI's model: another provider still holding it was never given a model of its own.
    model: provider !== 'openai' && savedModel === DEFAULT_MODEL ? TTS_MODEL_OPTIONS[provider][0].value : savedModel,
    voice: own.ttsVoice || TTS_VOICE_OPTIONS[provider][0].value,
    keySaved: Boolean(own.ttsApiKey?.trim()),
  };
}
