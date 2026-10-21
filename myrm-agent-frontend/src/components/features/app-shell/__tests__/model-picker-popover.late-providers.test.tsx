import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ModelPickerPopover from '../model-picker-popover';
import useProviderStore from '@/store/useProviderStore';
import type { ProviderConfig } from '@/store/config/providerTypes';

vi.mock('@/store/useOrgModelPolicyStore', () => ({
  useOrgModelPolicyStore: () => ({
    restricted: false,
    initialized: true,
    loadPolicy: vi.fn(),
    isModelAllowed: () => true,
  }),
}));

vi.mock('@/components/features/settings/model-service/ProviderIcon', () => ({
  default: () => <span data-testid="provider-icon" />,
}));

vi.mock('@/components/features/app-shell/capability-icons', () => ({
  default: () => null,
}));

vi.mock('@/services/llm-config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/llm-config')>();
  return {
    ...actual,
    fetchModelCapabilitiesBatch: vi.fn().mockResolvedValue({}),
    fetchModelSwitchPreflight: vi.fn().mockResolvedValue({}),
  };
});

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="popover-content">{children}</div>
  ),
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const lateProvider = {
  id: 'minimax',
  name: 'MiniMax',
  providerType: 'openai-like',
  isEnabled: true,
  apiUrl: 'https://api.example.com/v1',
  apiKeys: [{ key: 'sk-test', isActive: true }],
  enabledModels: ['model-late'],
} as unknown as ProviderConfig;

describe('ModelPickerPopover provider config arriving after mount', () => {
  beforeEach(() => {
    useProviderStore.setState({ providers: [] });
  });

  it('lists models once the provider store finishes loading', async () => {
    render(
      <ModelPickerPopover
        currentSelection={null}
        onSelect={vi.fn()}
        trigger={<button type="button">open</button>}
      />,
    );
    expect(screen.queryByTestId('model-item-minimax-model-late')).not.toBeInTheDocument();

    await act(async () => {
      useProviderStore.setState({ providers: [lateProvider] });
    });

    expect(await screen.findByTestId('model-item-minimax-model-late')).toBeInTheDocument();
  });
});
