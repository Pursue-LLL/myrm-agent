import { describe, expect, it } from 'vitest';

import type { ProviderConfig } from '@/store/config/providerTypes';
import type { BuiltinToolId } from '@/store/chat/types';
import type {
  ImageGenerationConfig,
  VideoGenerationConfig,
  VoiceConfigValue,
} from '@/services/config/types';
import {
  collectMediaCredentialWarnings,
  isImageMediaCredentialReady,
  isTtsMediaCredentialReady,
  isVideoMediaCredentialReady,
  providerHasActiveApiKey,
} from '../mediaCredentialReadiness';

const openaiProvider: ProviderConfig = {
  id: 'openai',
  name: 'OpenAI',
  isBuiltIn: true,
  isEnabled: true,
  routingProfile: 'openai',
  apiKeys: [{ id: 'key-1', key: 'sk-live', remark: '', isActive: true }],
  apiUrl: '',
  enabledModels: [],
  availableModels: [],
};

const disabledProvider: ProviderConfig = {
  id: 'openai',
  name: 'OpenAI',
  isBuiltIn: true,
  isEnabled: false,
  routingProfile: 'openai',
  apiKeys: [{ id: 'key-1', key: 'sk-live', remark: '', isActive: true }],
  apiUrl: '',
  enabledModels: [],
  availableModels: [],
};

const imageConfig: ImageGenerationConfig = {
  model: 'dall-e-3',
  fallbackModels: [],
  defaultSize: '1024x1024',
  defaultQuality: 'standard',
  timeoutSeconds: 60,
  maxRetries: 2,
};

const videoConfig: VideoGenerationConfig = {
  provider: 'openai',
  model: 'gpt-video-1',
  fallbackProviders: [],
  timeoutSeconds: 120,
  maxRetries: 2,
};

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
  ttsApiKey: '',
  ttsBaseUrl: '',
  ttsVoice: '',
  ttsMaxLength: 4000,
  ttsSummaryEnabled: false,
  ttsSummaryThreshold: 0,
  ttsSummaryModel: '',
};

describe('mediaCredentialReadiness', () => {
  it('detects active provider api keys', () => {
    expect(providerHasActiveApiKey([openaiProvider], 'openai')).toBe(true);
    expect(providerHasActiveApiKey([disabledProvider], 'openai')).toBe(false);
    expect(providerHasActiveApiKey([], 'openai')).toBe(false);
  });

  it('flags image credential missing when dall-e provider has no key', () => {
    expect(isImageMediaCredentialReady([], imageConfig)).toBe(false);
    expect(isImageMediaCredentialReady([openaiProvider], imageConfig)).toBe(true);
  });

  it('flags video credential missing without provider key or status', () => {
    expect(isVideoMediaCredentialReady([], videoConfig, {})).toBe(false);
    expect(
      isVideoMediaCredentialReady([], videoConfig, {
        openai: { hasApiKey: true, name: 'OpenAI', healthy: true, configured: true },
      }),
    ).toBe(true);
  });

  it('treats edge TTS as always ready', () => {
    expect(isTtsMediaCredentialReady([], { ...ttsConfig, ttsProvider: 'edge' })).toBe(true);
  });

  it('collects warnings only for enabled media tools without credentials', () => {
    const enabled: BuiltinToolId[] = ['web_search', 'image_generation', 'video_generation', 'tts'];
    const warnings = collectMediaCredentialWarnings(
      enabled,
      [],
      imageConfig,
      videoConfig,
      ttsConfig,
      {},
    );
    expect(warnings).toEqual(['image_generation', 'video_generation', 'tts']);
  });

  it('returns no warnings when credentials exist for enabled media tools', () => {
    const enabled: BuiltinToolId[] = ['image_generation', 'video_generation', 'tts'];
    const warnings = collectMediaCredentialWarnings(
      enabled,
      [openaiProvider],
      imageConfig,
      videoConfig,
      { ...ttsConfig, ttsApiKey: 'sk-tts' },
      { openai: { hasApiKey: true, name: 'OpenAI', healthy: true, configured: true } },
    );
    expect(warnings).toEqual([]);
  });
});
