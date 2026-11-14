/**
 * What the thinking-intensity choice does to the model parameters a request carries: `auto` asks nothing, so a
 * depth configured on the model stays; any other choice, including `off`, replaces it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  setGlobalCustomValue,
  setGlobalIntensity,
} from '@/components/features/message-input-actions/ThinkingIntensityButton';
import type { DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';
import { getInitialDefaultModelConfig } from '@/store/config/providerTypes';

const providerState: {
  providers: ProviderConfig[];
  defaultModelConfig: DefaultModelConfig;
  getModelInfo: () => { extraParams?: Record<string, unknown> };
} = {
  providers: [],
  defaultModelConfig: getInitialDefaultModelConfig(),
  getModelInfo: () => ({}),
};

vi.mock('@/store/useProviderStore', () => ({
  default: {
    getState: () => providerState,
  },
}));

import { getModelSelection } from '@/store/chat/modelSelection';

function configureModel(extraParams?: Record<string, unknown>) {
  providerState.providers = [
    {
      id: 'opencode_go',
      name: 'OpenCode Go',
      isBuiltIn: true,
      isEnabled: true,
      apiKeys: [{ id: 'k1', key: 'sk-test', remark: 'default', isActive: true }],
      apiUrl: 'https://opencode.ai/zen/go/v1',
      enabledModels: ['deepseek-v4.1-flash'],
      availableModels: ['deepseek-v4.1-flash'],
      routingProfile: 'openai',
    },
  ];
  providerState.defaultModelConfig = {
    ...getInitialDefaultModelConfig(),
    baseModel: {
      ...getInitialDefaultModelConfig().baseModel,
      primary: { providerId: 'opencode_go', model: 'deepseek-v4.1-flash' },
    },
  };
  providerState.getModelInfo = () => ({ extraParams });
}

function requestedEffort(): unknown {
  return getModelSelection('agent', null)?.modelKwargs?.reasoning_effort;
}

describe('getModelSelection thinking effort', () => {
  beforeEach(() => {
    setGlobalIntensity('auto');
    configureModel();
  });

  it('carries no effort while the intensity is auto', () => {
    expect(getModelSelection('agent', null)?.modelKwargs).not.toHaveProperty('reasoning_effort');
  });

  it('keeps the depth configured on the model while the intensity is auto', () => {
    configureModel({ reasoning_effort: 'high' });

    expect(requestedEffort()).toBe('high');
  });

  it('replaces the configured depth with the level the user chose', () => {
    configureModel({ reasoning_effort: 'high' });
    setGlobalIntensity('low');

    expect(requestedEffort()).toBe('low');
  });

  it('carries off as the user asking for no thinking, even over a configured depth', () => {
    configureModel({ reasoning_effort: 'high' });
    setGlobalIntensity('off');

    expect(requestedEffort()).toBe('off');
  });

  it('carries a custom value as the effort', () => {
    setGlobalCustomValue('16k');

    expect(requestedEffort()).toBe('16k');
  });
});
