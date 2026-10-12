/**
 * Default-on smart routing picks its light / reasoning models from the user's enabled models by cost.
 * A routed turn drives the full tool loop, so models known to lack function calling must never be picked.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { getLightModelSelection, getReasoningModelSelection } from '@/store/chat/messageRequest';
import { getInitialDefaultModelConfig, type CustomModelInfo } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';

const INFO_BASE = { source: 'api', lastUpdated: '2026-01-01T00:00:00Z' } as const;

function modelInfo(inputCost: number, supportsFunctionCalling?: boolean): CustomModelInfo {
  return { ...INFO_BASE, input_cost_per_million: inputCost, supports_function_calling: supportsFunctionCalling };
}

function setProvider(models: Record<string, CustomModelInfo>): void {
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
    defaultModelConfig: getInitialDefaultModelConfig(),
    customModelInfo: Object.fromEntries(names.map((name) => [`acme/${name}`, models[name]])),
  });
}

describe('auto-selected routing models', () => {
  beforeEach(() => {
    useProviderStore.setState({
      providers: [],
      customModelInfo: {},
      defaultModelConfig: getInitialDefaultModelConfig(),
    });
  });

  it('picks the cheapest model for the light tier', () => {
    setProvider({ cheap: modelInfo(0.1, true), mid: modelInfo(1, true), pricey: modelInfo(10, true) });

    expect(getLightModelSelection()?.model).toBe('cheap');
  });

  it('skips a cheaper model that is known to lack function calling', () => {
    setProvider({ 'cheap-no-tools': modelInfo(0.05, false), cheap: modelInfo(0.1, true), pricey: modelInfo(10, true) });

    expect(getLightModelSelection()?.model).toBe('cheap');
  });

  it('skips a more expensive model that is known to lack function calling for the reasoning tier', () => {
    setProvider({ cheap: modelInfo(0.1, true), strong: modelInfo(5, true), 'strong-no-tools': modelInfo(20, false) });

    expect(getReasoningModelSelection()?.model).toBe('strong');
  });

  it('keeps models whose function-calling support is unknown', () => {
    setProvider({ 'cheap-unknown': modelInfo(0.05), pricey: modelInfo(10, true) });

    expect(getLightModelSelection()?.model).toBe('cheap-unknown');
  });

  it('disables auto routing instead of failing when fewer than two usable models remain', () => {
    setProvider({ 'cheap-no-tools': modelInfo(0.05, false), only: modelInfo(1, true) });

    expect(getLightModelSelection()).toBeNull();
    expect(getReasoningModelSelection()).toBeNull();
  });
});
