import { describe, expect, it } from 'vitest';

import { resolveImageProviderId, VIDEO_PROVIDER_CONFIG_IDS } from '../mediaProviderStatus';

describe('mediaProviderStatus', () => {
  it('maps dall-e models to openai provider id', () => {
    expect(resolveImageProviderId('dall-e-3')).toBe('openai');
  });

  it('maps gemini/imagen models to gemini provider id', () => {
    expect(resolveImageProviderId('gemini/imagen-3')).toBe('gemini');
    expect(resolveImageProviderId('models/imagen-3')).toBe('gemini');
  });

  it('maps flux and stability prefixes', () => {
    expect(resolveImageProviderId('flux/schnell')).toBe('together_ai');
    expect(resolveImageProviderId('stability/sdxl')).toBe('stability');
  });

  it('exposes video provider config id mapping', () => {
    expect(VIDEO_PROVIDER_CONFIG_IDS.openai).toBe('openai');
    expect(VIDEO_PROVIDER_CONFIG_IDS.qwen).toBe('dashscope');
  });
});
