import { describe, expect, it } from 'vitest';
import { resolveModelPickerTriggerDisplay } from '@/lib/model-binding';
import type { AgentConfig } from '@/store/chat/types';
import type { DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';

const providers: ProviderConfig[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    isEnabled: true,
    enabledModels: ['gpt-4o'],
    providerType: 'openai',
    apiKey: 'sk-test',
    baseUrl: '',
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
    const display = resolveModelPickerTriggerDisplay(
      'agent',
      agentConfig,
      defaultModelConfig,
      providers,
      'default',
    );
    expect(display.modelName).toBe('gpt-4o');
    expect(display.moaPresetId).toBe('default');
  });

  it('clears MoA chip outside agent mode', () => {
    const display = resolveModelPickerTriggerDisplay(
      'fast',
      agentConfig,
      defaultModelConfig,
      providers,
      'default',
    );
    expect(display.moaPresetId).toBeNull();
  });
});
