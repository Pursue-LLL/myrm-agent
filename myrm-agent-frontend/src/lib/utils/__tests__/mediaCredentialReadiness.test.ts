import { describe, expect, it } from 'vitest';

import type { ProviderConfig } from '@/store/config/providerTypes';
import type { BuiltinToolId } from '@/store/chat/types';
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
  isEnabled: true,
  routingProfile: 'openai',
  apiKeys: [{ key: 'sk-live', isActive: true }],
  models: [],
};

const disabledProvider: ProviderConfig = {
  id: 'openai',
  name: 'OpenAI',
  isEnabled: false,
  routingProfile: 'openai',
  apiKeys: [{ key: 'sk-live', isActive: true }],
  models: [],
};

describe('mediaCredentialReadiness', () => {
  it('detects active provider api keys', () => {
    expect(providerHasActiveApiKey([openaiProvider], 'openai')).toBe(true);
    expect(providerHasActiveApiKey([disabledProvider], 'openai')).toBe(false);
    expect(providerHasActiveApiKey([], 'openai')).toBe(false);
  });

  it('flags image credential missing when dall-e provider has no key', () => {
    expect(isImageMediaCredentialReady([], { model: 'dall-e-3' })).toBe(false);
    expect(isImageMediaCredentialReady([openaiProvider], { model: 'dall-e-3' })).toBe(true);
  });

  it('flags video credential missing without provider key or status', () => {
    expect(isVideoMediaCredentialReady([], { provider: 'openai' }, {})).toBe(false);
    expect(
      isVideoMediaCredentialReady([], { provider: 'openai' }, { openai: { hasApiKey: true } }),
    ).toBe(true);
  });

  it('treats edge TTS as always ready', () => {
    expect(isTtsMediaCredentialReady([], { ttsProvider: 'edge' })).toBe(true);
  });

  it('collects warnings only for enabled media tools without credentials', () => {
    const enabled: BuiltinToolId[] = ['web_search', 'image_generation', 'video_generation', 'tts'];
    const warnings = collectMediaCredentialWarnings(
      enabled,
      [],
      { model: 'dall-e-3' },
      { provider: 'openai' },
      { ttsProvider: 'openai' },
      {},
    );
    expect(warnings).toEqual(['image_generation', 'video_generation', 'tts']);
  });

  it('returns no warnings when credentials exist for enabled media tools', () => {
    const enabled: BuiltinToolId[] = ['image_generation', 'video_generation', 'tts'];
    const warnings = collectMediaCredentialWarnings(
      enabled,
      [openaiProvider],
      { model: 'dall-e-3' },
      { provider: 'openai' },
      { ttsProvider: 'openai', ttsApiKey: 'sk-tts' },
      { openai: { hasApiKey: true } },
    );
    expect(warnings).toEqual([]);
  });
});
