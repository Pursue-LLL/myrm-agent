import { describe, expect, it } from 'vitest';

import { getInitialDefaultModelConfig } from '../providerTypes';
import {
  findRecommendedVisionFallbackSelection,
  hasConfiguredVisionCapability,
  hasVisionFallbackForVideo,
  shouldOfferVisionFallbackRecommendation,
} from '../visionCapability';

describe('visionCapability', () => {
  const getModelInfo = (providerId: string, model: string) => {
    if (providerId === 'openai' && model === 'gpt-4o-mini') {
      return { supports_vision: true };
    }
    if (providerId === 'openai' && model === 'gpt-4o') {
      return { supports_vision: true };
    }
    if (providerId === 'deepseek' && model === 'deepseek-chat') {
      return { supports_vision: false };
    }
    return undefined;
  };

  it('detects vision via slot fallback when primary is empty', () => {
    const config = {
      ...getInitialDefaultModelConfig(),
      baseModel: {
        primary: { providerId: 'deepseek', model: 'deepseek-chat' },
        fallback: null,
      },
      visionFallbackModel: {
        primary: null,
        fallback: { providerId: 'openai', model: 'gpt-4o' },
      },
    };

    expect(hasConfiguredVisionCapability(config, getModelInfo)).toBe(true);
  });

  it('detects vision via base model when no vision slot is configured', () => {
    const config = {
      ...getInitialDefaultModelConfig(),
      baseModel: {
        primary: { providerId: 'openai', model: 'gpt-4o' },
        fallback: null,
      },
      visionFallbackModel: null,
    };

    expect(hasConfiguredVisionCapability(config, getModelInfo)).toBe(true);
  });

  it('returns false when no vision path exists', () => {
    const config = {
      ...getInitialDefaultModelConfig(),
      baseModel: {
        primary: { providerId: 'deepseek', model: 'deepseek-chat' },
        fallback: null,
      },
      visionFallbackModel: null,
    };

    expect(hasConfiguredVisionCapability(config, getModelInfo)).toBe(false);
    expect(hasVisionFallbackForVideo(config, getModelInfo)).toBe(false);
  });

  it('offers recommendation when base is text-only and vision slot is empty', () => {
    const config = {
      ...getInitialDefaultModelConfig(),
      baseModel: {
        primary: { providerId: 'deepseek', model: 'deepseek-chat' },
        fallback: null,
      },
      visionFallbackModel: null,
    };

    expect(shouldOfferVisionFallbackRecommendation(config, getModelInfo)).toBe(true);
  });

  it('finds first enabled vision model in provider order', () => {
    const enabledModels = [
      { providerId: 'deepseek', providerName: 'DeepSeek', model: 'deepseek-chat' },
      { providerId: 'openai', providerName: 'OpenAI', model: 'gpt-4o-mini' },
    ];

    expect(
      findRecommendedVisionFallbackSelection(enabledModels, getModelInfo, {
        providerId: 'deepseek',
        model: 'deepseek-chat',
      }),
    ).toEqual({ providerId: 'openai', model: 'gpt-4o-mini' });
  });

  it('does not offer recommendation when base model already supports vision', () => {
    const config = {
      ...getInitialDefaultModelConfig(),
      baseModel: {
        primary: { providerId: 'openai', model: 'gpt-4o' },
        fallback: null,
      },
      visionFallbackModel: null,
    };

    expect(shouldOfferVisionFallbackRecommendation(config, getModelInfo)).toBe(false);
  });
});
