import { describe, expect, it } from 'vitest';

import {
  isTtsProvider,
  isTtsSelected,
  readStoredChoices,
  TTS_MODEL_OPTIONS,
  TTS_PROVIDER_OPTIONS,
  TTS_VOICE_OPTIONS,
} from '../ttsCatalog';

describe('ttsCatalog', () => {
  it('offers models and voices for exactly the providers it lists', () => {
    const providers = TTS_PROVIDER_OPTIONS.map((option) => option.value).sort();

    expect(Object.keys(TTS_MODEL_OPTIONS).sort()).toEqual(providers);
    expect(Object.keys(TTS_VOICE_OPTIONS).sort()).toEqual(providers);
    for (const provider of providers) {
      expect(isTtsProvider(provider)).toBe(true);
    }
  });

  it.each(['edge', 'piper', 'voicebox', '', undefined])('does not offer %j', (provider) => {
    expect(isTtsProvider(provider)).toBe(false);
  });
});

describe('isTtsSelected', () => {
  it('needs an offered provider with a model and a voice', () => {
    expect(isTtsSelected('openai', 'tts-1', 'alloy')).toBe(true);
    expect(isTtsSelected('openai', 'tts-1', '')).toBe(false);
    expect(isTtsSelected('openai', ' ', 'alloy')).toBe(false);
    expect(isTtsSelected('openai', undefined, undefined)).toBe(false);
    expect(isTtsSelected('edge', 'tts-1', 'alloy')).toBe(false);
    expect(isTtsSelected(undefined, 'tts-1', 'alloy')).toBe(false);
  });
});

describe('readStoredChoices', () => {
  it('reports nothing chosen, not defaults, for settings that name nothing', () => {
    expect(readStoredChoices({})).toEqual({ provider: '', model: '', voice: '', keySaved: false });
    expect(readStoredChoices({ sttEnabled: true, ttsMaxLength: 900 })).toEqual({
      provider: '',
      model: '',
      voice: '',
      keySaved: false,
    });
  });

  it('reports exactly what is stored for an offered provider, without filling gaps', () => {
    expect(
      readStoredChoices({ ttsProvider: 'elevenlabs', ttsModel: 'eleven_turbo_v2_5', ttsVoice: '', ttsApiKey: ' sk ' }),
    ).toEqual({ provider: 'elevenlabs', model: 'eleven_turbo_v2_5', voice: '', keySaved: true });
    expect(readStoredChoices({ ttsProvider: 'volcengine', ttsModel: 'tts-1' })).toEqual({
      provider: 'volcengine',
      model: 'tts-1',
      voice: '',
      keySaved: false,
    });
  });

  it.each(['edge', 'piper', 'voicebox'])(
    'keeps only the provider when the channel voice settings hold %s: its model, voice and key mean nothing here',
    (ttsProvider) => {
      expect(
        readStoredChoices({
          ttsProvider,
          ttsModel: 'gpt-4o-mini-tts',
          ttsVoice: 'en-US-AriaNeural',
          ttsApiKey: 'sk-of-another-provider',
        }),
      ).toEqual({ provider: ttsProvider, model: '', voice: '', keySaved: false });
    },
  );
});
