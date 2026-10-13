import { describe, expect, it } from 'vitest';
import { resolveSmartRouting } from '@/lib/model-routing';
import type { AgentConfig } from '@/store/chat/types';
import {
  getInitialDefaultModelConfig,
  type CustomModelInfo,
  type DefaultModelConfig,
  type ModelSlot,
  type ProviderConfig,
  type RoutingConfig,
} from '@/store/config/providerTypes';

const INFO_BASE = { source: 'api', lastUpdated: '2026-01-01T00:00:00Z' } as const;

function modelInfo(inputCost: number | undefined, supportsFunctionCalling?: boolean): CustomModelInfo {
  return { ...INFO_BASE, input_cost_per_million: inputCost, supports_function_calling: supportsFunctionCalling };
}

function provider(id: string, models: string[], overrides: Partial<ProviderConfig> = {}): ProviderConfig {
  return {
    id,
    name: id,
    isBuiltIn: false,
    isEnabled: true,
    apiKeys: [{ id: `${id}-key`, key: 'sk-test', remark: 'default', isActive: true }],
    apiUrl: 'https://api.example.com/v1',
    enabledModels: models,
    availableModels: models,
    routingProfile: 'openai',
    ...overrides,
  };
}

const PRICED_PROVIDERS = [provider('acme', ['cheap', 'mid', 'pricey'])];
const PRICED_INFO: Record<string, CustomModelInfo> = {
  'acme/cheap': modelInfo(0.1, true),
  'acme/mid': modelInfo(1, true),
  'acme/pricey': modelInfo(10, true),
};

const emptySlot = (): ModelSlot => ({ primary: null, fallback: null });

function routingConfig(overrides: Partial<RoutingConfig> = {}): RoutingConfig {
  return { enabled: true, lightModel: emptySlot(), reasoningModel: emptySlot(), ...overrides };
}

function defaults(routing: RoutingConfig | null = null): DefaultModelConfig {
  return { ...getInitialDefaultModelConfig(), routingConfig: routing };
}

function agent(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return { agentId: 'agent-1', ...overrides } as AgentConfig;
}

const PIN = { providerId: 'acme', model: 'mid' };

function resolve(
  actionMode: 'fast' | 'agent' | 'deep_research',
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[] = PRICED_PROVIDERS,
  customModelInfo: Record<string, CustomModelInfo> = PRICED_INFO,
) {
  return resolveSmartRouting(actionMode, agentConfig, defaultModelConfig, providers, customModelInfo);
}

describe('resolveSmartRouting — default-on activation', () => {
  it('routes an untouched default user in agent mode with auto-picked cost tiers', () => {
    const routing = resolve('agent', null, defaults());

    expect(routing.active).toBe(true);
    expect(routing.canSelect).toBe(true);
    expect(routing.light.primary).toEqual({ providerId: 'acme', model: 'cheap' });
    expect(routing.reasoning.primary).toEqual({ providerId: 'acme', model: 'pricey' });
  });

  it('routes an agent that has no pinned model', () => {
    expect(resolve('agent', agent(), defaults()).active).toBe(true);
  });

  it('does not route fast mode and does not offer the routing entry there', () => {
    const routing = resolve('fast', null, defaults());

    expect(routing.active).toBe(false);
    expect(routing.canSelect).toBe(false);
  });

  it('keeps deep research routed because it ignores agent-pinned models', () => {
    const routing = resolve('deep_research', agent({ modelSelection: PIN }), defaults());

    expect(routing.active).toBe(true);
    expect(routing.light.primary?.model).toBe('cheap');
    expect(routing.canSelect).toBe(false);
  });
});

describe('resolveSmartRouting — explicit choices win', () => {
  it('does not route an agent pinned to a model, but keeps the entry to return to routing', () => {
    const routing = resolve('agent', agent({ modelSelection: PIN }), defaults());

    expect(routing.active).toBe(false);
    expect(routing.canSelect).toBe(true);
  });

  it('keeps a pinned agent un-routed even when routing is explicitly enabled by default', () => {
    const routing = resolve('agent', agent({ modelSelection: PIN }), defaults(routingConfig()));

    expect(routing.active).toBe(false);
  });

  it('routes a pinned agent that explicitly enabled its own routing', () => {
    const routing = resolve('agent', agent({ modelSelection: PIN, routingConfig: routingConfig() }), defaults());

    expect(routing.active).toBe(true);
  });

  it('never routes an agent that explicitly disabled routing, even with default routing enabled', () => {
    const routing = resolve(
      'agent',
      agent({ routingConfig: routingConfig({ enabled: false }) }),
      defaults(routingConfig()),
    );

    expect(routing.active).toBe(false);
    expect(routing.canSelect).toBe(false);
  });

  it('never routes when default routing is disabled and the agent inherits it', () => {
    const routing = resolve('agent', agent(), defaults(routingConfig({ enabled: false })));

    expect(routing.active).toBe(false);
    expect(routing.canSelect).toBe(false);
  });

  it('lets an agent that enabled its own routing override a disabled default', () => {
    const routing = resolve(
      'agent',
      agent({ routingConfig: routingConfig() }),
      defaults(routingConfig({ enabled: false })),
    );

    expect(routing.active).toBe(true);
  });
});

describe('resolveSmartRouting — slot resolution', () => {
  it('does not route when fewer than two priced models are usable, even if explicitly enabled', () => {
    const providers = [provider('acme', ['only', 'cheap-no-tools'])];
    const info = { 'acme/only': modelInfo(1, true), 'acme/cheap-no-tools': modelInfo(0.05, false) };

    const routing = resolve('agent', null, defaults(routingConfig()), providers, info);

    expect(routing.active).toBe(false);
    expect(routing.canSelect).toBe(false);
    expect(routing.light.primary).toBeNull();
    expect(routing.reasoning.primary).toBeNull();
  });

  it('skips models known to lack function calling but keeps unknown ones', () => {
    const providers = [provider('acme', ['no-tools', 'unknown', 'pricey', 'pricey-no-tools'])];
    const info = {
      'acme/no-tools': modelInfo(0.01, false),
      'acme/unknown': modelInfo(0.05),
      'acme/pricey': modelInfo(10, true),
      'acme/pricey-no-tools': modelInfo(50, false),
    };

    const routing = resolve('agent', null, defaults(), providers, info);

    expect(routing.light.primary?.model).toBe('unknown');
    expect(routing.reasoning.primary?.model).toBe('pricey');
  });

  it('ignores models with unknown prices and providers that are disabled or lack credentials', () => {
    const providers = [
      provider('acme', ['cheap', 'pricey', 'unpriced']),
      provider('off', ['free'], { isEnabled: false }),
      provider('nokey', ['free2'], { apiKeys: [] }),
    ];
    const info = {
      'acme/cheap': modelInfo(0.1, true),
      'acme/pricey': modelInfo(10, true),
      'acme/unpriced': modelInfo(undefined, true),
      'off/free': modelInfo(0.001, true),
      'nokey/free2': modelInfo(0.002, true),
    };

    const routing = resolve('agent', null, defaults(), providers, info);

    expect(routing.light.primary?.model).toBe('cheap');
    expect(routing.reasoning.primary?.model).toBe('pricey');
  });

  it('breaks price ties by enabled-model order', () => {
    const providers = [provider('acme', ['a', 'b', 'c', 'd'])];
    const info = {
      'acme/a': modelInfo(1, true),
      'acme/b': modelInfo(1, true),
      'acme/c': modelInfo(9, true),
      'acme/d': modelInfo(9, true),
    };

    const routing = resolve('agent', null, defaults(), providers, info);

    expect(routing.light.primary?.model).toBe('a');
    expect(routing.reasoning.primary?.model).toBe('c');
  });

  it('routes with configured default slots when no model has a known price', () => {
    const providers = [provider('acme', ['small', 'big'])];
    const config = routingConfig({
      lightModel: { primary: { providerId: 'acme', model: 'small' }, fallback: null, modelKwargs: { top_p: 0.5 } },
      reasoningModel: {
        primary: { providerId: 'acme', model: 'big' },
        fallback: { providerId: 'acme', model: 'small' },
      },
    });

    const routing = resolve('agent', null, defaults(config), providers, {});

    expect(routing.active).toBe(true);
    expect(routing.light).toEqual({
      primary: { providerId: 'acme', model: 'small' },
      fallback: null,
      modelKwargs: { top_p: 0.5 },
    });
    expect(routing.reasoning.primary).toEqual({ providerId: 'acme', model: 'big' });
    expect(routing.reasoning.fallback).toEqual({ providerId: 'acme', model: 'small' });
  });

  it('prefers agent slots over default slots and agent fallbacks over default fallbacks', () => {
    const defaultSlots = routingConfig({
      lightModel: { primary: { providerId: 'acme', model: 'cheap' }, fallback: { providerId: 'acme', model: 'mid' } },
      reasoningModel: {
        primary: { providerId: 'acme', model: 'pricey' },
        fallback: { providerId: 'acme', model: 'mid' },
      },
    });
    const agentSlots = routingConfig({
      lightModel: { primary: { providerId: 'acme', model: 'mid' }, fallback: { providerId: 'acme', model: 'pricey' } },
      reasoningModel: { primary: null, fallback: null },
    });

    const routing = resolve('agent', agent({ routingConfig: agentSlots }), defaults(defaultSlots));

    expect(routing.light.primary?.model).toBe('mid');
    expect(routing.light.fallback?.model).toBe('pricey');
    expect(routing.reasoning.primary?.model).toBe('pricey');
    expect(routing.reasoning.fallback?.model).toBe('mid');
  });
});
