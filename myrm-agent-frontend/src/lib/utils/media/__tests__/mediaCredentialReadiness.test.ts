import { describe, expect, it } from 'vitest';

import type { ProviderConfig } from '@/store/config/providerTypes';
import type { BuiltinToolId } from '@/store/chat/types';
import type { ImageGenerationConfig, VideoGenerationConfig, VoiceConfigValue } from '@/services/config/types';
import type { MediaProviderStatus } from '../mediaProviderStatus';
import {
  collectMediaCredentialWarnings,
  imageToolSetup,
  providerHasActiveApiKey,
  ttsToolSetup,
  videoToolSetup,
} from '../mediaCredentialReadiness';

const providerWithKey = (id: string, overrides: Partial<ProviderConfig> = {}): ProviderConfig => ({
  id,
  name: id,
  isBuiltIn: true,
  isEnabled: true,
  routingProfile: id,
  apiKeys: [{ id: 'key-1', key: 'sk-live', remark: '', isActive: true }],
  apiUrl: '',
  enabledModels: [],
  availableModels: [],
  ...overrides,
});

const openaiProvider = providerWithKey('openai');
const disabledProvider = providerWithKey('openai', { isEnabled: false });

const imageConfig: ImageGenerationConfig = {
  model: 'gpt-image-2.6-sunburst',
  fallbackModels: [],
  defaultSize: '1024x1024',
  timeoutSeconds: 60,
  maxRetries: 2,
};

const videoConfig: VideoGenerationConfig = {
  provider: 'gemini',
  model: 'veo-3.1-fast-generate-preview',
  fallbackProviders: [],
  timeoutSeconds: 120,
  maxRetries: 2,
};

const geminiStatus = (overrides: Partial<MediaProviderStatus> = {}): MediaProviderStatus => ({
  name: 'Google Veo',
  hasApiKey: false,
  healthy: false,
  configured: false,
  defaultModel: 'veo-3.1-fast-generate-preview',
  models: [{ id: 'veo-3.1-fast-generate-preview', name: 'Veo 3.1 Fast' }],
  ...overrides,
});

const ttsConfig: VoiceConfigValue = {
  sttEnabled: false,
  sttProvider: '',
  sttApiKey: '',
  sttModel: '',
  sttLanguage: '',
  sttLocalModel: '',
  sttLocalDevice: '',
  sttLocalComputeType: '',
  sttBaseUrl: '',
  ttsMode: '',
  ttsProvider: 'openai',
  ttsModel: 'tts-1',
  ttsApiKey: '',
  ttsBaseUrl: '',
  ttsVoice: 'alloy',
  ttsMaxLength: 4000,
  ttsSummaryEnabled: false,
  ttsSummaryThreshold: 0,
  ttsSummaryModel: '',
};

describe('providerHasActiveApiKey', () => {
  it('detects active provider api keys', () => {
    expect(providerHasActiveApiKey([openaiProvider], 'openai')).toBe(true);
    expect(providerHasActiveApiKey([disabledProvider], 'openai')).toBe(false);
    expect(providerHasActiveApiKey([], 'openai')).toBe(false);
  });
});

describe('imageToolSetup', () => {
  it('is notSelected for no choice, however many keys exist', () => {
    expect(imageToolSetup([openaiProvider], undefined)).toBe('notSelected');
  });

  it.each(['dall-e-3', 'gpt-image-1', ''])('is notSelected for %j, a model the engine no longer offers', (model) => {
    expect(imageToolSetup([openaiProvider], { ...imageConfig, model })).toBe('notSelected');
  });

  it('needs the key of the provider of the chosen model', () => {
    expect(imageToolSetup([], imageConfig)).toBe('noCredential');
    expect(imageToolSetup([openaiProvider], imageConfig)).toBe('ready');
    expect(imageToolSetup([openaiProvider], { ...imageConfig, model: 'flux/pro' })).toBe('noCredential');
    expect(imageToolSetup([providerWithKey('together_ai')], { ...imageConfig, model: 'flux/pro' })).toBe('ready');
  });
});

describe('videoToolSetup', () => {
  it('is notSelected for no choice, or a provider or model left empty', () => {
    expect(videoToolSetup([openaiProvider], undefined, {})).toBe('notSelected');
    expect(videoToolSetup([], { ...videoConfig, model: '' }, {})).toBe('notSelected');
  });

  it('is notSelected for a stored provider the server no longer lists', () => {
    const stale = { ...videoConfig, provider: 'openai' as VideoGenerationConfig['provider'], model: 'sora' };

    expect(videoToolSetup([openaiProvider], stale, { gemini: geminiStatus({ hasApiKey: true }) })).toBe('notSelected');
    expect(videoToolSetup([openaiProvider], stale, {})).toBe('notSelected');
  });

  it('is notSelected when the listed provider does not serve the chosen model', () => {
    const status = { gemini: geminiStatus({ hasApiKey: true }) };

    expect(videoToolSetup([], { ...videoConfig, model: 'retired-model' }, status)).toBe('notSelected');
  });

  it('is ready on the key the server reports or on one in the provider table', () => {
    expect(videoToolSetup([], videoConfig, { gemini: geminiStatus({ hasApiKey: true }) })).toBe('ready');
    expect(videoToolSetup([providerWithKey('gemini')], videoConfig, { gemini: geminiStatus() })).toBe('ready');
    expect(videoToolSetup([providerWithKey('gemini')], videoConfig, {})).toBe('ready');
  });

  it('needs a key', () => {
    expect(videoToolSetup([], videoConfig, { gemini: geminiStatus() })).toBe('noCredential');
    expect(videoToolSetup([], videoConfig, {})).toBe('noCredential');
  });

  it('looks a provider up under its provider-table id', () => {
    const qwen = { ...videoConfig, provider: 'qwen' as const, model: 'wan2.6-t2v' };

    expect(videoToolSetup([providerWithKey('dashscope')], qwen, {})).toBe('ready');
    expect(videoToolSetup([providerWithKey('qwen')], qwen, {})).toBe('noCredential');
  });
});

describe('ttsToolSetup', () => {
  it('is notSelected for no settings, or a provider, model or voice left empty', () => {
    expect(ttsToolSetup([openaiProvider], null)).toBe('notSelected');
    expect(ttsToolSetup([openaiProvider], { ...ttsConfig, ttsProvider: '' })).toBe('notSelected');
    expect(ttsToolSetup([openaiProvider], { ...ttsConfig, ttsModel: '' })).toBe('notSelected');
    expect(ttsToolSetup([openaiProvider], { ...ttsConfig, ttsVoice: '  ' })).toBe('notSelected');
  });

  it.each(['edge', 'piper', 'voicebox'])(
    'is notSelected for %s, a provider only channel replies can use',
    (ttsProvider) => {
      expect(ttsToolSetup([], { ...ttsConfig, ttsProvider })).toBe('notSelected');
    },
  );

  it('is ready on the key saved with the voice settings or on one in the provider table', () => {
    expect(ttsToolSetup([], { ...ttsConfig, ttsApiKey: 'sk-tts' })).toBe('ready');
    expect(ttsToolSetup([openaiProvider], ttsConfig)).toBe('ready');
  });

  it('needs a key', () => {
    expect(ttsToolSetup([], ttsConfig)).toBe('noCredential');
  });
});

describe('collectMediaCredentialWarnings', () => {
  const enabled: BuiltinToolId[] = ['web_search', 'image_generation', 'video_generation', 'tts'];

  it('says, per enabled media tool, whether a choice or a key is missing', () => {
    const warnings = collectMediaCredentialWarnings(
      enabled,
      [],
      { ...imageConfig, model: 'dall-e-3' },
      videoConfig,
      { ...ttsConfig, ttsProvider: 'edge' },
      { gemini: geminiStatus() },
    );

    expect(warnings).toEqual([
      { tool: 'image_generation', reason: 'notSelected' },
      { tool: 'video_generation', reason: 'noCredential' },
      { tool: 'tts', reason: 'notSelected' },
    ]);
  });

  it('warns about nothing chosen at all, even when the provider table holds keys', () => {
    const warnings = collectMediaCredentialWarnings(enabled, [openaiProvider], undefined, undefined, null, {});

    expect(warnings.map((warning) => warning.reason)).toEqual(['notSelected', 'notSelected', 'notSelected']);
  });

  it('leaves out media tools the Agent has not enabled', () => {
    expect(collectMediaCredentialWarnings(['web_search'], [], undefined, undefined, null, {})).toEqual([]);
    expect(
      collectMediaCredentialWarnings(['tts'], [], undefined, undefined, ttsConfig, {}).map((warning) => warning.tool),
    ).toEqual(['tts']);
  });

  it('returns no warnings when every enabled tool is chosen and has its key', () => {
    const warnings = collectMediaCredentialWarnings(
      enabled,
      [openaiProvider],
      imageConfig,
      videoConfig,
      { ...ttsConfig, ttsApiKey: 'sk-tts' },
      { gemini: geminiStatus({ hasApiKey: true }) },
    );

    expect(warnings).toEqual([]);
  });
});
