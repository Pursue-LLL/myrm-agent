import { describe, expect, it } from 'vitest';
import { resolveModelPickerTriggerDisplay } from '@/lib/model-binding';
import type { AgentConfig } from '@/store/chat/types';
import type { CustomModelInfo, DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';

const providers: ProviderConfig[] = [
  {
    id: 'openai',
    routingProfile: 'openai',
    name: 'OpenAI',
    isBuiltIn: true,
    isEnabled: true,
    enabledModels: ['gpt-4o', 'gpt-4o-mini'],
    availableModels: ['gpt-4o', 'gpt-4o-mini'],
    providerType: 'openai-like',
    apiUrl: '',
    apiKeys: [{ id: 'key-1', key: 'sk-test', remark: 'test', isActive: true }],
  },
];

const pricedModelInfo: Record<string, CustomModelInfo> = {
  'openai/gpt-4o': { source: 'api', lastUpdated: '2026-01-01T00:00:00Z', input_cost_per_million: 2.5 },
  'openai/gpt-4o-mini': { source: 'api', lastUpdated: '2026-01-01T00:00:00Z', input_cost_per_million: 0.15 },
};

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
      pricedModelInfo,
      'default',
    );
    expect(display.modelName).toBe('gpt-4o');
    expect(display.moaPresetId).toBe('default');
    expect(display.isSmartRouting).toBe(false);
  });

  it('clears MoA chip outside agent mode', () => {
    const display = resolveModelPickerTriggerDisplay(
      'fast',
      agentConfig,
      defaultModelConfig,
      providers,
      pricedModelInfo,
      'default',
    );
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
      pricedModelInfo,
      null,
    );
    expect(display.isSmartRouting).toBe(true);
    expect(display.modelName).toBeNull();
    expect(display.canSelectSmartRouting).toBe(true);
  });

  it('activates smart routing for an untouched default config when priced models exist', () => {
    const noRoutingAgent = { agentId: 'agent-1', modelSelection: null } as unknown as AgentConfig;

    const display = resolveModelPickerTriggerDisplay(
      'agent',
      noRoutingAgent,
      defaultModelConfig,
      providers,
      pricedModelInfo,
      null,
    );
    expect(display.isSmartRouting).toBe(true);
    expect(display.canSelectSmartRouting).toBe(true);
  });

  it('does not claim smart routing when no model has a known price', () => {
    const noRoutingAgent = { agentId: 'agent-1', modelSelection: null } as unknown as AgentConfig;

    const display = resolveModelPickerTriggerDisplay('agent', noRoutingAgent, defaultModelConfig, providers, {}, null);
    expect(display.isSmartRouting).toBe(false);
    expect(display.canSelectSmartRouting).toBe(false);
    expect(display.modelName).toBe('gpt-4o');
  });

  it('overrides smart routing when single model is explicitly chosen', () => {
    const routingDefaultModelConfig = {
      ...defaultModelConfig,
      routingConfig: { enabled: true },
    } as DefaultModelConfig;

    const display = resolveModelPickerTriggerDisplay(
      'agent',
      agentConfig,
      routingDefaultModelConfig,
      providers,
      pricedModelInfo,
      null,
    );
    expect(display.isSmartRouting).toBe(false);
    expect(display.modelName).toBe('gpt-4o');
    expect(display.canSelectSmartRouting).toBe(true);
  });
});
