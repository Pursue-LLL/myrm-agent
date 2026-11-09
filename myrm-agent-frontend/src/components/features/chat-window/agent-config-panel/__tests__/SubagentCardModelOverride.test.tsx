/** @vitest-environment jsdom */

/**
 * [INPUT]
 * - ../SubagentCard::SubagentCard, EphemeralSubagentConfig
 * - @/store/useProviderStore (mocked provider catalogue)
 * - @/components/features/settings/default-model/EnabledModelSelect (stubbed trigger)
 *
 * [OUTPUT]
 * - Tests: the model override stores the routed `providerId/model` name the server reads,
 *   and an empty selection leaves the field absent so the sub-agent inherits the parent LLM.
 *
 * [POS]
 * Contract test pinning the key and value shape `SubagentCard` hands to the server; the request
 * payload carries these objects verbatim, and the server only reads `model`.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import type { ProviderConfig } from '@/store/config/providerTypes';

const providers: ProviderConfig[] = [
  {
    id: 'openai_like',
    routingProfile: 'openai',
    name: 'OpenAI-compatible',
    isBuiltIn: false,
    isEnabled: true,
    apiKeys: [{ id: 'k1', key: 'sk-test', remark: '', isActive: true }],
    apiUrl: '',
    enabledModels: ['deepseek-chat'],
    availableModels: ['deepseek-chat'],
  },
  {
    id: 'anthropic',
    routingProfile: 'anthropic',
    name: 'Anthropic',
    isBuiltIn: true,
    isEnabled: true,
    apiKeys: [{ id: 'k2', key: 'sk-ant', remark: '', isActive: true }],
    apiUrl: '',
    enabledModels: ['claude-sonnet-4'],
    availableModels: ['claude-sonnet-4'],
  },
];

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (state: { providers: ProviderConfig[] }) => unknown) => selector({ providers }),
  selectEnabledModels: (list: ProviderConfig[]) =>
    list
      .filter((provider) => provider.isEnabled && provider.apiKeys.some((key) => key.isActive && key.key))
      .flatMap((provider) =>
        provider.enabledModels.map((model) => ({ providerId: provider.id, providerName: provider.name, model })),
      ),
}));

vi.mock('@/components/features/settings/default-model/EnabledModelSelect', () => ({
  default: (props: {
    value: { providerId: string; model: string } | null;
    onChange: (selection: { providerId: string; model: string } | null) => void;
    placeholder?: string;
  }) => (
    <div data-testid="model-select" data-value={JSON.stringify(props.value)}>
      <span>{props.placeholder}</span>
      <button type="button" onClick={() => props.onChange({ providerId: 'openai_like', model: 'deepseek-chat' })}>
        pick-inherit-target
      </button>
      <button type="button" onClick={() => props.onChange(null)}>
        pick-inherit
      </button>
    </div>
  ),
}));

import { SubagentCard, type EphemeralSubagentConfig } from '../SubagentCard';

const t = (key: string) => key;

function renderCard(config: EphemeralSubagentConfig, onModelChange = vi.fn()) {
  render(
    <SubagentCard
      subagentKey="researcher"
      config={config}
      onDisplayNameChange={vi.fn()}
      onThemeColorChange={vi.fn()}
      onControlScopeChange={vi.fn()}
      onModelChange={onModelChange}
      onDelete={vi.fn()}
      t={t}
    />,
  );
  return onModelChange;
}

describe('SubagentCard model override', () => {
  beforeEach(() => vi.clearAllMocks());

  it('writes the routed provider/model name the server materializes', () => {
    const onModelChange = renderCard({ display_name: 'Researcher', theme_color: 'blue', control_scope: 'leaf' });

    screen.getByText('pick-inherit-target').click();

    expect(onModelChange).toHaveBeenCalledWith('researcher', 'openai_like/deepseek-chat');
  });

  it('clears the field so the sub-agent inherits the parent LLM', () => {
    const onModelChange = renderCard({
      display_name: 'Researcher',
      model: 'openai_like/deepseek-chat',
    });

    screen.getByText('pick-inherit').click();

    expect(onModelChange).toHaveBeenCalledWith('researcher', undefined);
  });

  it('shows a stored routed name as the selected model', () => {
    renderCard({ model: 'anthropic/claude-sonnet-4' });

    expect(screen.getByTestId('model-select').dataset.value).toBe(
      JSON.stringify({ providerId: 'anthropic', model: 'claude-sonnet-4' }),
    );
  });

  it('leaves the selection empty when no model is configured', () => {
    renderCard({});

    expect(screen.getByTestId('model-select').dataset.value).toBe('null');
  });
});
