import { describe, expect, it } from 'vitest';

import { resolveImageProviderId, VIDEO_PROVIDER_CONFIG_IDS, videoProviderConfigId } from '../mediaProviderStatus';

describe('mediaProviderStatus', () => {
  it('maps the OpenAI image models to the openai provider id', () => {
    expect(resolveImageProviderId('gpt-image-2.6-sunburst')).toBe('openai');
    expect(resolveImageProviderId('gpt-image-2.6-flare')).toBe('openai');
  });

  it('maps gemini/imagen models to gemini provider id', () => {
    expect(resolveImageProviderId('gemini/imagen-3')).toBe('gemini');
    expect(resolveImageProviderId('models/imagen-3')).toBe('gemini');
  });

  it('maps flux and stability prefixes', () => {
    expect(resolveImageProviderId('flux/schnell')).toBe('together_ai');
    expect(resolveImageProviderId('stability/sdxl')).toBe('stability');
  });

  it('maps the xAI image models to the xai provider id', () => {
    expect(resolveImageProviderId('xai/grok-imagine-image')).toBe('xai');
  });

  it('exposes video provider config id mapping for the six providers the server offers', () => {
    expect(Object.keys(VIDEO_PROVIDER_CONFIG_IDS).sort()).toEqual([
      'fal',
      'gemini',
      'minimax',
      'qwen',
      'volcengine',
      'xai',
    ]);
    expect(VIDEO_PROVIDER_CONFIG_IDS.qwen).toBe('dashscope');
  });

  it('looks a stored video provider up under its provider-table id, and finds none for a retired one', () => {
    expect(videoProviderConfigId('qwen')).toBe('dashscope');
    expect(videoProviderConfigId('gemini')).toBe('gemini');
    expect(videoProviderConfigId('openai')).toBeUndefined();
    expect(videoProviderConfigId('')).toBeUndefined();
  });
});
