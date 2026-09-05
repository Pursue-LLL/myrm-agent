import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ModelPickerPopover from '../model-picker-popover';
import type { ModelCapabilities } from '@/services/llm-config';

const getEnabledModels = vi.fn();
const providers = vi.fn(
  () =>
    [] as Array<{
      id: string;
      name: string;
      isEnabled: boolean;
      enabledModels: string[];
      providerType: string;
      customApiUrl?: string;
    }>,
);
const customModelInfo = vi.fn(
  () =>
    ({}) as Record<
      string,
      {
        supports_vision?: boolean;
        supports_function_calling?: boolean;
        supports_reasoning?: boolean;
        supports_audio_input?: boolean;
        supports_video_input?: boolean;
        max_input_tokens?: number;
        input_cost_per_million?: number;
        output_cost_per_million?: number;
      }
    >,
);

vi.mock('@/store/useProviderStore', () => ({
  default: () => ({
    providers: providers(),
    getEnabledModels: () => getEnabledModels(),
    customModelInfo: customModelInfo(),
  }),
}));

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

const mocks = vi.hoisted(() => {
  return {
    fetchModelCapabilitiesBatch: vi.fn(),
    fetchModelSwitchPreflight: vi.fn(),
  };
});

vi.mock('@/services/llm-config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/llm-config')>();
  return {
    ...actual,
    fetchModelCapabilitiesBatch: mocks.fetchModelCapabilitiesBatch,
    fetchModelSwitchPreflight: mocks.fetchModelSwitchPreflight,
  };
});

// Popover needs to open; use a real trigger button and force open state
vi.mock('@/components/primitives/popover', () => {
  return {
    Popover: ({ children, onOpenChange }: { children: React.ReactNode; onOpenChange?: (open: boolean) => void }) => {
      const { useEffect } = require('react') as typeof import('react');
      useEffect(() => {
        onOpenChange?.(true);
      }, []);
      return <div>{children}</div>;
    },
    PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    PopoverContent: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="popover-content">{children}</div>
    ),
  };
});

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

function mockProviderState() {
  providers.mockReturnValue([
    { id: 'p1', name: 'Provider One', isEnabled: true, enabledModels: ['model-a'], providerType: 'openai' },
  ]);
  getEnabledModels.mockReturnValue([{ providerId: 'p1', providerName: 'Provider One', model: 'model-a' }]);
  customModelInfo.mockReturnValue({});
}

const caps: ModelCapabilities = {
  supports_vision: false,
  supports_function_calling: true,
  supports_reasoning: false,
  supports_audio_input: false,
  supports_video_input: false,
  supports_web_search: false,
  supports_prompt_caching: false,
  input_cost_per_token: null,
  output_cost_per_token: null,
  max_tokens: null,
  max_input_tokens: 16000,
  max_output_tokens: null,
};

const renderPopover = (
  props: {
    estimatedTokens?: number | null;
    compressStartRatio?: number | null;
    promptMode?: string | null;
    turnCount?: number | null;
    chatId?: string | null;
    onSelect?: (providerId: string, model: string) => void;
  } = {},
) => {
  const onSelect = props.onSelect ?? vi.fn();
  render(
    <ModelPickerPopover
      currentSelection={{ providerId: 'p1', model: 'model-a' }}
      onSelect={onSelect}
      estimatedTokens={props.estimatedTokens}
      compressStartRatio={props.compressStartRatio ?? null}
      promptMode={props.promptMode ?? null}
      turnCount={props.turnCount ?? null}
      chatId={props.chatId ?? null}
      trigger={<button type="button">open</button>}
    />,
  );
  return { onSelect };
};

describe('ModelPickerPopover preflight warning', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProviderState();
    mocks.fetchModelCapabilitiesBatch.mockResolvedValue({
      'p1/model-a': caps,
    });
  });

  it('shows compress warning badge when preflight predicts compression', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({
      'p1/model-a': {
        model: 'p1/model-a',
        found: true,
        new_window: 16000,
        compress_threshold: 8266,
        will_compress: true,
      },
    });

    renderPopover({ estimatedTokens: 9000 });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    const badge = await screen.findByTestId('preflight-warning-p1-model-a');
    expect(badge).toBeInTheDocument();
  });

  it('does not show warning when preflight says no compression', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({
      'p1/model-a': {
        model: 'p1/model-a',
        found: true,
        new_window: 16000,
        compress_threshold: 8266,
        will_compress: false,
      },
    });

    renderPopover({ estimatedTokens: 1000 });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.queryByTestId('preflight-warning-p1-model-a')).not.toBeInTheDocument();
  });

  it('skips preflight when estimatedTokens is not provided', async () => {
    renderPopover();

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.fetchModelSwitchPreflight).not.toHaveBeenCalled();
    expect(screen.queryByTestId('preflight-warning-p1-model-a')).not.toBeInTheDocument();
  });

  it('hides warning after two acknowledged selections (anti-nagging)', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({
      results: [
        {
          model: 'p1/model-a',
          found: true,
          new_window: 16000,
          compress_threshold: 8266,
          will_compress: true,
        },
      ],
    });

    const { onSelect } = renderPopover({ estimatedTokens: 9000 });

    // Open popover and confirm model selection twice to acknowledge the warning
    for (let i = 0; i < 2; i += 1) {
      await act(async () => {
        await Promise.resolve();
        await Promise.resolve();
      });
      const modelButton = screen.getByText('model-a');
      fireEvent.click(modelButton);
      expect(onSelect).toHaveBeenCalledTimes(i + 1);
    }

    // Warning hidden after 2 acknowledgements
    await waitFor(() => {
      expect(screen.queryByTestId('preflight-warning-p1-model-a')).not.toBeInTheDocument();
    });
  });

  it('passes compressStartRatio to the preflight service', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({ results: [] });

    renderPopover({ estimatedTokens: 9000, compressStartRatio: 0.6 });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledWith(
      9000,
      expect.arrayContaining([expect.objectContaining({ model: 'p1/model-a', max_input_tokens: 16000 })]),
      0.6,
      null,
      null,
      null,
    );
  });

  it('passes promptMode to the preflight service', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({ results: [] });

    renderPopover({ estimatedTokens: 9000, promptMode: 'lean', turnCount: 7 });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledWith(9000, expect.any(Array), null, 'lean', 7, null);
  });

  it('re-fetches preflight when turnCount grows past the dynamic-threshold window', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({ results: [] });

    const { rerender } = render(
      <ModelPickerPopover
        currentSelection={{ providerId: 'p1', model: 'model-a' }}
        onSelect={vi.fn()}
        estimatedTokens={9000}
        compressStartRatio={null}
        promptMode={null}
        turnCount={3}
        trigger={<button type="button">open</button>}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledTimes(1);
    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledWith(9000, expect.any(Array), null, null, 3, undefined);

    rerender(
      <ModelPickerPopover
        currentSelection={{ providerId: 'p1', model: 'model-a' }}
        onSelect={vi.fn()}
        estimatedTokens={9000}
        compressStartRatio={null}
        promptMode={null}
        turnCount={10}
        trigger={<button type="button">open</button>}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledTimes(2);
    expect(mocks.fetchModelSwitchPreflight).toHaveBeenLastCalledWith(
      9000,
      expect.any(Array),
      null,
      null,
      10,
      undefined,
    );
  });

  it('re-fetches preflight when promptMode changes mid-session', async () => {
    mocks.fetchModelSwitchPreflight.mockResolvedValue({ results: [] });

    const { rerender } = render(
      <ModelPickerPopover
        currentSelection={{ providerId: 'p1', model: 'model-a' }}
        onSelect={vi.fn()}
        estimatedTokens={9000}
        compressStartRatio={null}
        promptMode={null}
        trigger={<button type="button">open</button>}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledTimes(1);

    rerender(
      <ModelPickerPopover
        currentSelection={{ providerId: 'p1', model: 'model-a' }}
        onSelect={vi.fn()}
        estimatedTokens={9000}
        compressStartRatio={null}
        promptMode="lean"
        trigger={<button type="button">open</button>}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(mocks.fetchModelSwitchPreflight).toHaveBeenCalledTimes(2);
  });
});

describe('ModelPickerPopover local-owned marginal cost badge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders $0/M badge for built-in ollama local model when pricing is null', async () => {
    providers.mockReturnValue([
      { id: 'ollama', name: 'Ollama', isEnabled: true, enabledModels: ['llama3'], providerType: 'ollama' },
    ]);
    getEnabledModels.mockReturnValue([{ providerId: 'ollama', providerName: 'Ollama', model: 'llama3' }]);
    customModelInfo.mockReturnValue({});

    mocks.fetchModelCapabilitiesBatch.mockResolvedValue({
      'ollama/llama3': {
        ...caps,
        input_cost_per_token: null,
        output_cost_per_token: null,
      },
    });

    render(
      <ModelPickerPopover
        currentSelection={{ providerId: 'ollama', model: 'llama3' }}
        onSelect={vi.fn()}
        trigger={<button type="button">open</button>}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText('$0/M')).toBeInTheDocument();
  });

  it('renders $0/M badge for trusted split-stack LAN provider without explicit pricing', async () => {
    providers.mockReturnValue([
      {
        id: 'split-stack-vllm',
        name: 'LAN vLLM',
        isEnabled: true,
        enabledModels: ['qwen2.5'],
        providerType: 'openai-compatible',
        apiUrl: 'http://192.168.1.188:8000/v1',
      },
    ]);
    getEnabledModels.mockReturnValue([
      { providerId: 'split-stack-vllm', providerName: 'LAN vLLM', model: 'qwen2.5' },
    ]);
    customModelInfo.mockReturnValue({});

    mocks.fetchModelCapabilitiesBatch.mockResolvedValue({
      'split-stack-vllm/qwen2.5': {
        ...caps,
        input_cost_per_token: null,
        output_cost_per_token: null,
      },
    });

    render(
      <ModelPickerPopover
        currentSelection={{ providerId: 'split-stack-vllm', model: 'qwen2.5' }}
        onSelect={vi.fn()}
        trigger={<button type="button">open</button>}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('$0/M')).toBeInTheDocument();
    });
  });

  it('respects explicit custom model pricing and does not force $0/M', async () => {
    providers.mockReturnValue([
      {
        id: 'ollama',
        name: 'Ollama Proxy',
        isEnabled: true,
        enabledModels: ['custom-paid'],
        providerType: 'ollama',
      },
    ]);
    getEnabledModels.mockReturnValue([
      { providerId: 'ollama', providerName: 'Ollama Proxy', model: 'custom-paid' },
    ]);
    customModelInfo.mockReturnValue({
      'ollama/custom-paid': {
        supports_vision: false,
        supports_function_calling: true,
        supports_reasoning: false,
        supports_audio_input: false,
        supports_video_input: false,
        max_input_tokens: 32000,
        input_cost_per_million: 2.5,
        output_cost_per_million: 10,
      },
    });

    render(
      <ModelPickerPopover
        currentSelection={{ providerId: 'ollama', model: 'custom-paid' }}
        onSelect={vi.fn()}
        trigger={<button type="button">open</button>}
      />,
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getByText('$2.5/M')).toBeInTheDocument();
  });
});

