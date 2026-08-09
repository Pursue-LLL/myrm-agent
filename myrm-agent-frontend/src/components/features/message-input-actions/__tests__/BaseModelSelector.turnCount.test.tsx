/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockChatMessages = vi.hoisted(
  () => [] as Array<{
    role: string;
    contextBudget?: { turn_count?: number; current_tokens?: number; messages_estimated_tokens?: number };
  }>,
);
const mockAgentConfig = vi.hoisted(() => ({ engineParams: { compress_start_ratio: 0.4 }, promptMode: 'full' }));

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: object) => unknown) =>
    selector({
      agentConfig: mockAgentConfig,
      actionMode: 'agent',
      activeMoaPresetId: null,
      updateAgentConfig: vi.fn(),
      setActiveMoaPresetId: vi.fn(),
      messages: mockChatMessages,
    }),
  ),
}));

vi.mock('@/store/useProviderStore', () => ({
  default: vi.fn((selector: (state: object) => unknown) =>
    selector({
      providers: [
        { id: 'p1', name: 'Provider One', isEnabled: true, enabledModels: ['model-a'], providerType: 'openai' },
      ],
      defaultModelConfig: null,
      getEnabledModels: () => [{ providerId: 'p1', providerName: 'Provider One', model: 'model-a' }],
      setBaseModel: vi.fn(),
      setBaseModelFallback: vi.fn(),
      setFastModeModel: vi.fn(),
      isInitialized: true,
      initProviders: vi.fn(),
    }),
  ),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/moaPresetUtils', () => ({
  isMoaPresetConfigured: () => false,
  listMoaPresetOptions: () => [],
  isActiveMoaPresetAvailable: () => false,
  resolveMoaPresetLabelKey: () => null,
}));

vi.mock('@/lib/model-binding', () => ({
  resolveActiveModelSelection: () => ({ providerId: 'p1', model: 'model-a' }),
  resolveActiveFallbackSelection: () => null,
  resolveModelPickerTriggerDisplay: () => ({ modelName: 'model-a', moaPresetId: null }),
}));

const mockPopoverProps = vi.hoisted(() => vi.fn());
vi.mock('@/components/features/app-shell/model-picker-popover', () => ({
  default: (props: Record<string, unknown>) => {
    mockPopoverProps(props);
    return <div data-testid="popover-mock" />;
  },
}));

vi.mock('@/components/features/settings/model-service/ProviderIcon', () => ({
  default: () => <span data-testid="provider-icon" />,
}));

import BaseModelSelector from '../BaseModelSelector';

describe('BaseModelSelector turnCount source', () => {
  beforeEach(() => {
    mockChatMessages.length = 0;
    mockAgentConfig.engineParams = { compress_start_ratio: 0.4 };
    mockPopoverProps.mockClear();
  });

  it('prefers server turn_count from contextBudget over local counting', () => {
    mockChatMessages.push(
      { role: 'user' },
      { role: 'assistant' },
      { role: 'user' },
      {
        role: 'assistant',
        contextBudget: { turn_count: 30, current_tokens: 5000, messages_estimated_tokens: 4800 },
      },
    );

    render(<BaseModelSelector />);

    expect(mockPopoverProps).toHaveBeenCalled();
    const lastCall = mockPopoverProps.mock.calls[mockPopoverProps.mock.calls.length - 1][0];
    expect(lastCall.turnCount).toBe(30);
    expect(lastCall.estimatedTokens).toBe(5000);
  });

  it('falls back to local user-message count when contextBudget has no turn_count', () => {
    mockChatMessages.push(
      { role: 'user' },
      { role: 'assistant' },
      { role: 'user' },
      {
        role: 'assistant',
        contextBudget: { current_tokens: 4000, messages_estimated_tokens: 3800 },
      },
    );

    render(<BaseModelSelector />);

    const lastCall = mockPopoverProps.mock.calls[mockPopoverProps.mock.calls.length - 1][0];
    expect(lastCall.turnCount).toBe(2);
  });

  it('falls back to zero when no assistant contextBudget exists', () => {
    mockChatMessages.push({ role: 'user' }, { role: 'assistant' });

    render(<BaseModelSelector />);

    const lastCall = mockPopoverProps.mock.calls[mockPopoverProps.mock.calls.length - 1][0];
    expect(lastCall.turnCount).toBe(1);
    expect(lastCall.estimatedTokens).toBe(0);
  });

  it('uses server turn_count even when local messages are paginated (long session)', () => {
    // 模拟分页场景：本地只有最近 10 条（4 条 user），服务端快照上报真实 30 轮
    for (let i = 0; i < 6; i += 1) {
      mockChatMessages.push({ role: 'user' }, { role: 'assistant' });
    }
    mockChatMessages.push({ role: 'user' }, { role: 'assistant' }, { role: 'user' }, { role: 'assistant' });
    mockChatMessages.push({
      role: 'assistant',
      contextBudget: { turn_count: 30, current_tokens: 30000, messages_estimated_tokens: 28000 },
    });

    render(<BaseModelSelector />);

    const lastCall = mockPopoverProps.mock.calls[mockPopoverProps.mock.calls.length - 1][0];
    expect(lastCall.turnCount).toBe(30);
  });
});
