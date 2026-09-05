'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import SmartRoutingStep from '../SmartRoutingStep';

const mockSetRoutingEnabled = vi.fn();
const mockSetRoutingLightModel = vi.fn();
const mockSetRoutingReasoningModel = vi.fn();
let mockEnabledModels: Array<{ providerId: string; model: string }> = [];
let mockProviders: Array<{ id: string; providerType: string; apiUrl?: string; apiKeys: Array<{ key: string; isActive: boolean }> }> = [];
let mockDefaultModelConfig: { baseModel: { primary: { providerId: string; model: string } | null } } = {
  baseModel: { primary: null },
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconRoute: (props: Record<string, unknown>) => <svg data-testid="icon-route" {...props} />,
  IconZap: (props: Record<string, unknown>) => <svg data-testid="icon-zap" {...props} />,
  IconBrain: (props: Record<string, unknown>) => <svg data-testid="icon-brain" {...props} />,
  IconCpu: (props: Record<string, unknown>) => <svg data-testid="icon-cpu" {...props} />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) => {
    const state = {
      providers: mockProviders,
      getEnabledModels: () => mockEnabledModels,
      defaultModelConfig: mockDefaultModelConfig,
      setRoutingEnabled: mockSetRoutingEnabled,
      setRoutingLightModel: mockSetRoutingLightModel,
      setRoutingReasoningModel: mockSetRoutingReasoningModel,
    };
    return selector(state);
  },
}));

describe('SmartRoutingStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEnabledModels = [];
    mockProviders = [];
    mockDefaultModelConfig = { baseModel: { primary: null } };
  });

  it('correctly classifies and recommends deepseek-reasoner as reasoning model', () => {
    mockProviders = [
      {
        id: 'deepseek',
        providerType: 'openai-like',
        apiUrl: 'https://api.deepseek.com/v1',
        apiKeys: [{ key: 'sk-test', isActive: true }],
      },
    ];
    mockEnabledModels = [
      { providerId: 'deepseek', model: 'deepseek-chat' },
      { providerId: 'deepseek', model: 'deepseek-reasoner' },
    ];
    mockDefaultModelConfig = {
      baseModel: { primary: { providerId: 'deepseek', model: 'deepseek-chat' } },
    };

    const onComplete = vi.fn();
    const onSkip = vi.fn();
    render(<SmartRoutingStep onComplete={onComplete} onSkip={onSkip} />);

    expect(screen.getByText('deepseek-reasoner')).toBeDefined();
    expect(screen.getByText('reasoningLabel')).toBeDefined();

    const enableButton = screen.getByText('enableButton');
    fireEvent.click(enableButton);

    expect(mockSetRoutingEnabled).toHaveBeenCalledWith(true);
    expect(mockSetRoutingReasoningModel).toHaveBeenCalledWith({
      providerId: 'deepseek',
      model: 'deepseek-reasoner',
    });
    expect(onComplete).toHaveBeenCalled();
  });

  it('correctly classifies gemini thinking models as reasoning', () => {
    mockProviders = [
      {
        id: 'google',
        providerType: 'gemini',
        apiKeys: [{ key: 'test-key', isActive: true }],
      },
    ];
    mockEnabledModels = [
      { providerId: 'google', model: 'gemini-2.0-flash' },
      { providerId: 'google', model: 'gemini-2.5-flash-thinking' },
    ];
    mockDefaultModelConfig = {
      baseModel: { primary: { providerId: 'google', model: 'gemini-2.0-flash' } },
    };

    const onComplete = vi.fn();
    render(<SmartRoutingStep onComplete={onComplete} onSkip={vi.fn()} />);

    expect(screen.getByText('gemini-2.5-flash-thinking')).toBeDefined();
  });

  it('heuristic topology fallback pairs local model with cloud model when names lack keywords', () => {
    mockProviders = [
      {
        id: 'ollama',
        providerType: 'openai-like',
        apiUrl: 'http://127.0.0.1:11434/v1',
        apiKeys: [],
      },
      {
        id: 'anthropic',
        providerType: 'anthropic',
        apiKeys: [{ key: 'sk-ant-test', isActive: true }],
      },
    ];
    mockEnabledModels = [
      { providerId: 'ollama', model: 'qwen2.5:32b' },
      { providerId: 'anthropic', model: 'claude-3-5-sonnet' },
    ];
    mockDefaultModelConfig = {
      baseModel: { primary: { providerId: 'anthropic', model: 'claude-3-5-sonnet' } },
    };

    const onComplete = vi.fn();
    render(<SmartRoutingStep onComplete={onComplete} onSkip={vi.fn()} />);

    expect(screen.getByText('qwen2.5:32b')).toBeDefined();
    expect(screen.getByText('liteLabel')).toBeDefined();

    const enableButton = screen.getByText('enableButton');
    fireEvent.click(enableButton);

    expect(mockSetRoutingEnabled).toHaveBeenCalledWith(true);
    expect(mockSetRoutingLightModel).toHaveBeenCalledWith({
      providerId: 'ollama',
      model: 'qwen2.5:32b',
    });
    expect(onComplete).toHaveBeenCalled();
  });

  it('triggers onSkip when skip button is clicked', () => {
    const onSkip = vi.fn();
    render(<SmartRoutingStep onComplete={vi.fn()} onSkip={onSkip} />);

    const skipButton = screen.getByText('skipButton');
    fireEvent.click(skipButton);

    expect(onSkip).toHaveBeenCalled();
  });
});
