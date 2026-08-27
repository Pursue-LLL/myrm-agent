import { describe, expect, it } from 'vitest';
import { resolveModelPickerTriggerDisplay } from '@/lib/model-binding';
import type { AgentConfig } from '@/store/chat/types';
import type { DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';

const providers: ProviderConfig[] = [
  {
    id: 'openai',
    routingProfile: 'openai',
    name: 'OpenAI',
    isBuiltIn: true,
    isEnabled: true,
    enabledModels: ['gpt-4o'],
    availableModels: ['gpt-4o'],
    providerType: 'openai-like',
    apiUrl: '',
    apiKeys: [{ id: 'key-1', key: 'sk-test', remark: 'test', isActive: true }],
  },
];

const defaultModelConfig = {
  baseModel: {
    primary: { providerId: 'openai', model: 'gpt-4o' },
    temperature: 0.7,
    modelKwargs: {},
  },
} as DefaultModelConfig;

const agentConfig = {
  agentId: 'agent-1',
  modelSelection: { providerId: 'openai', model: 'gpt-4o' },
} as AgentConfig;

describe('resolveModelPickerTriggerDisplay', () => {
  it('shows primary model and MoA chip when preset is active', () => {
    const display = resolveModelPickerTriggerDisplay('agent', agentConfig, defaultModelConfig, providers, 'default');
    expect(display.modelName).toBe('gpt-4o');
    expect(display.moaPresetId).toBe('default');
    expect(display.isSmartRouting).toBe(false);
  });

  it('clears MoA chip outside agent mode', () => {
    const display = resolveModelPickerTriggerDisplay('fast', agentConfig, defaultModelConfig, providers, 'default');
    expect(display.moaPresetId).toBeNull();
  });

  it('activates smart routing when enabled and no explicit single model override is set', () => {
    const routingDefaultModelConfig = {
      ...defaultModelConfig,
      routingConfig: { enabled: true },
    } as DefaultModelConfig;

    const autoAgentConfig = {
      agentId: 'agent-1',
      modelSelection: null,
    } as unknown as AgentConfig;

    const display = resolveModelPickerTriggerDisplay(
      'agent',
      autoAgentConfig,
      routingDefaultModelConfig,
      providers,
      null,
    );
    expect(display.isSmartRouting).toBe(true);
    expect(display.modelName).toBeNull();
  });

  it('overrides smart routing when single model is explicitly chosen', () => {
    const routingDefaultModelConfig = {
      ...defaultModelConfig,
      routingConfig: { enabled: true },
    } as DefaultModelConfig;

    const display = resolveModelPickerTriggerDisplay('agent', agentConfig, routingDefaultModelConfig, providers, null);
    expect(display.isSmartRouting).toBe(false);
    expect(display.modelName).toBe('gpt-4o');
  });
});
