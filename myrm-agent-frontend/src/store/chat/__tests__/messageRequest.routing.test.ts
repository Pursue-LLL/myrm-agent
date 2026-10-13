/**
 * The routing slots a request carries must match what the model picker claims: a turn the UI shows as
 * routed carries light / reasoning slots, a turn it shows as pinned or fast carries none.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { resolveModelPickerTriggerDisplay } from '@/lib/model-binding';
import { getRoutingModelSelections } from '@/store/chat/messageRequest';
import type { ActionMode, AgentConfig } from '@/store/chat/types';
import { getInitialDefaultModelConfig, type CustomModelInfo, type RoutingConfig } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';

const INFO_BASE = { source: 'api', lastUpdated: '2026-01-01T00:00:00Z' } as const;

const modelInfo = (inputCost: number): CustomModelInfo => ({
  ...INFO_BASE,
  input_cost_per_million: inputCost,
  supports_function_calling: true,
});

function seedProviders(routingConfig: RoutingConfig | null = null, models: Record<string, CustomModelInfo> = {}) {
  const names = Object.keys(models);
  useProviderStore.setState({
    providers: [
      {
        id: 'acme',
        name: 'Acme',
        isBuiltIn: false,
        isEnabled: true,
        apiKeys: [{ id: 'k1', key: 'sk-test', remark: 'default', isActive: true }],
        apiUrl: 'https://api.example.com/v1',
        enabledModels: names,
        availableModels: names,
        routingProfile: 'openai',
      },
    ],
    defaultModelConfig: {
      ...getInitialDefaultModelConfig(),
      baseModel: { primary: { providerId: 'acme', model: 'mid' }, fallback: null },
      routingConfig,
    },
    customModelInfo: Object.fromEntries(names.map((name) => [`acme/${name}`, models[name]])),
  });
}

const PRICED = { cheap: modelInfo(0.1), mid: modelInfo(1), pricey: modelInfo(10) };
const PIN = { providerId: 'acme', model: 'mid' };

function agent(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return { agentId: 'agent-1', ...overrides } as AgentConfig;
}

function uiClaimsRouting(actionMode: ActionMode, agentConfig: AgentConfig | null): boolean {
  const { providers, defaultModelConfig, customModelInfo } = useProviderStore.getState();
  return resolveModelPickerTriggerDisplay(actionMode, agentConfig, defaultModelConfig, providers, customModelInfo, null)
    .isSmartRouting;
}

function requestRoutes(actionMode: ActionMode, agentConfig: AgentConfig | null): boolean {
  const selections = getRoutingModelSelections(actionMode, agentConfig);
  return Boolean(selections.light || selections.reasoning);
}

describe('request routing slots', () => {
  beforeEach(() => {
    useProviderStore.setState({
      providers: [],
      customModelInfo: {},
      defaultModelConfig: getInitialDefaultModelConfig(),
    });
  });

  it('attaches auto-picked cost tiers for an untouched default user', () => {
    seedProviders(null, PRICED);

    const selections = getRoutingModelSelections('agent', null);

    expect(selections.light?.model).toBe('cheap');
    expect(selections.reasoning?.model).toBe('pricey');
  });

  it('attaches no slots in fast mode, for a pinned agent, or when routing is switched off', () => {
    seedProviders(null, PRICED);
    expect(requestRoutes('fast', null)).toBe(false);
    expect(requestRoutes('agent', agent({ modelSelection: PIN }))).toBe(false);

    seedProviders(
      {
        enabled: false,
        lightModel: { primary: null, fallback: null },
        reasoningModel: { primary: null, fallback: null },
      },
      PRICED,
    );
    expect(requestRoutes('agent', null)).toBe(false);
  });

  it('attaches no slots when fewer than two priced models are usable', () => {
    seedProviders(null, { only: modelInfo(1) });

    expect(requestRoutes('agent', null)).toBe(false);
  });

  it('keeps the research model slot for deep research even when the agent pins a model', () => {
    seedProviders(null, PRICED);

    expect(getRoutingModelSelections('deep_research', agent({ modelSelection: PIN })).light?.model).toBe('cheap');
  });

  it('carries configured slot kwargs and fallbacks into the request selections', () => {
    seedProviders(
      {
        enabled: true,
        lightModel: {
          primary: { providerId: 'acme', model: 'cheap' },
          fallback: { providerId: 'acme', model: 'mid' },
          modelKwargs: { top_p: 0.5 },
        },
        reasoningModel: { primary: { providerId: 'acme', model: 'pricey' }, fallback: null },
      },
      PRICED,
    );

    const selections = getRoutingModelSelections('agent', null);

    expect(selections.light?.modelKwargs).toMatchObject({ top_p: 0.5 });
    expect(selections.fallbackLight?.model).toBe('mid');
    expect(selections.reasoning?.model).toBe('pricey');
    expect(selections.fallbackReasoning).toBeNull();
  });

  it.each<[string, ActionMode, () => AgentConfig | null]>([
    ['default agent mode', 'agent', () => null],
    ['agent without pin', 'agent', () => agent()],
    ['fast mode', 'fast', () => null],
    ['deep research', 'deep_research', () => null],
    ['pinned agent', 'agent', () => agent({ modelSelection: PIN })],
    [
      'pinned agent with its own routing enabled',
      'agent',
      () =>
        agent({
          modelSelection: PIN,
          routingConfig: {
            enabled: true,
            lightModel: { primary: null, fallback: null },
            reasoningModel: { primary: null, fallback: null },
          },
        }),
    ],
    [
      'agent with routing disabled',
      'agent',
      () =>
        agent({
          routingConfig: {
            enabled: false,
            lightModel: { primary: null, fallback: null },
            reasoningModel: { primary: null, fallback: null },
          },
        }),
    ],
  ])('request and picker agree for %s', (_label, actionMode, buildAgent) => {
    seedProviders(null, PRICED);
    const agentConfig = buildAgent();

    expect(requestRoutes(actionMode, agentConfig)).toBe(uiClaimsRouting(actionMode, agentConfig));
  });
});
