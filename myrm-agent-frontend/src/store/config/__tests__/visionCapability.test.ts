import { describe, expect, it } from 'vitest';
import type { CustomModelInfo, DefaultModelConfig } from '../providerTypes';
import { hasVisionFallbackForVideo } from '../visionCapability';

function modelInfo(supportsVision: boolean, supportsVideoInput = false): CustomModelInfo {
  return {
    source: 'user',
    lastUpdated: '',
    supports_vision: supportsVision,
    supports_video_input: supportsVideoInput,
  };
}

describe('hasVisionFallbackForVideo', () => {
  it('prefers videoFallbackModel primary when it supports native video input', () => {
    const config: DefaultModelConfig = {
      baseModel: { primary: { providerId: 'openai', model: 'gpt-4o' }, fallback: null },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      videoFallbackModel: {
        primary: { providerId: 'google', model: 'gemini-2.5-flash' },
        fallback: null,
      },
    };
    const getModelInfo = (providerId: string, model: string) => {
      if (providerId === 'google' && model === 'gemini-2.5-flash') {
        return modelInfo(true, true);
      }
      return modelInfo(false, false);
    };

    expect(hasVisionFallbackForVideo(config, getModelInfo)).toBe(true);
  });

  it('falls back to visionFallbackModel when video slot lacks native video', () => {
    const config: DefaultModelConfig = {
      baseModel: { primary: { providerId: 'openai', model: 'gpt-4o' }, fallback: null },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      videoFallbackModel: {
        primary: { providerId: 'openai', model: 'gpt-4o' },
        fallback: null,
      },
      visionFallbackModel: {
        primary: { providerId: 'qwen', model: 'qwen-vl-max' },
        fallback: null,
      },
    };
    const getModelInfo = (providerId: string, model: string) => {
      if (providerId === 'qwen' && model === 'qwen-vl-max') {
        return modelInfo(true, false);
      }
      return modelInfo(false, false);
    };

    expect(hasVisionFallbackForVideo(config, getModelInfo)).toBe(true);
  });

  it('returns false when no video or vision fallback is configured', () => {
    const config: DefaultModelConfig = {
      baseModel: { primary: { providerId: 'openai', model: 'gpt-4o' }, fallback: null },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
    };
    const getModelInfo = () => modelInfo(false, false);

    expect(hasVisionFallbackForVideo(config, getModelInfo)).toBe(false);
  });
});
