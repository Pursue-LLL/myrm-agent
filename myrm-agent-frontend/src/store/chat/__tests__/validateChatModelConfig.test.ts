import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { AgentConfig } from '@/store/chat/types';
import type { DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';
import { getInitialDefaultModelConfig } from '@/store/config/providerTypes';

const showI18nToast = vi.fn();

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: (...args: unknown[]) => showI18nToast(...args),
}));

const providerState: {
  providers: ProviderConfig[];
  defaultModelConfig: DefaultModelConfig;
  getModelInfo: () => { supports_vision?: boolean };
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

import { validateChatModelConfig } from '@/store/chat/messageRequest';

const baseAgentConfig: AgentConfig = {
  selectedSkillIds: [],
  selectedMcpNames: [],
  systemPrompt: '',
  useGlobalInstruction: true,
};

describe('validateChatModelConfig', () => {
  beforeEach(() => {
    showI18nToast.mockReset();
    providerState.providers = [];
    providerState.defaultModelConfig = getInitialDefaultModelConfig();
  });

  it('blocks when no provider is configured', () => {
    const result = validateChatModelConfig('agent', null);

    expect(result.valid).toBe(false);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.modelNotConfigured.title',
      undefined,
      expect.objectContaining({
        descriptionKey: 'chat.modelNotConfigured.description',
      }),
    );
  });

  it('blocks when provider exists but default model is missing', () => {
    providerState.providers = [
      {
        id: 'minimax',
        name: 'MiniMax',
        isBuiltIn: true,
        isEnabled: true,
        apiKeys: [{ id: 'k1', key: 'sk-test', remark: 'default', isActive: true }],
        apiUrl: 'https://api.example.com/v1',
        enabledModels: ['MiniMax-M2'],
        availableModels: ['MiniMax-M2'],
        routingProfile: 'minimax',
      },
    ];
    providerState.defaultModelConfig = getInitialDefaultModelConfig();

    const result = validateChatModelConfig('agent', baseAgentConfig);

    expect(result.valid).toBe(false);
    expect(showI18nToast).toHaveBeenCalledWith(
      'chat.modelNotConfigured.title',
      undefined,
      expect.objectContaining({
        descriptionKey: 'chat.defaultModelNotConfigured.description',
        action: expect.objectContaining({
          label: 'chat.defaultModelNotConfigured.action',
        }),
      }),
    );
  });

  it('allows send when default model is configured and available', () => {
    providerState.providers = [
      {
        id: 'minimax',
        name: 'MiniMax',
        isBuiltIn: true,
        isEnabled: true,
        apiKeys: [{ id: 'k1', key: 'sk-test', remark: 'default', isActive: true }],
        apiUrl: 'https://api.example.com/v1',
        enabledModels: ['MiniMax-M2'],
        availableModels: ['MiniMax-M2'],
        routingProfile: 'minimax',
      },
    ];
    providerState.defaultModelConfig = {
      ...getInitialDefaultModelConfig(),
      baseModel: {
        ...getInitialDefaultModelConfig().baseModel,
        primary: { providerId: 'minimax', model: 'MiniMax-M2' },
      },
    };

    const result = validateChatModelConfig('agent', baseAgentConfig);

    expect(result.valid).toBe(true);
    expect(result.modelSelection).toMatchObject({
      providerId: 'minimax',
      model: 'MiniMax-M2',
    });
    expect(showI18nToast).not.toHaveBeenCalled();
  });
});
