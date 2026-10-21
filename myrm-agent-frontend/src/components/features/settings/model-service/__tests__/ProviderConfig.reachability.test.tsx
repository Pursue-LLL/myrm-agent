import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '@/components/primitives/tooltip';
import type { ProviderConfig as ProviderConfigType } from '@/store/config/providerTypes';
import ProviderConfig from '../ProviderConfig';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

const checkModelReachability = vi.fn();

vi.mock('@/services/llm-config', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/llm-config')>();
  return {
    ...actual,
    checkModelReachability: (...args: unknown[]) => checkModelReachability(...args),
  };
});

const provider: ProviderConfigType = {
  id: 'openai-like',
  routingProfile: 'openai',
  name: 'OpenCode Go',
  isBuiltIn: false,
  isEnabled: true,
  apiKeys: [{ id: 'key-1', key: 'sk-test', remark: '', isActive: true }],
  apiUrl: 'https://example.test/v1',
  enabledModels: ['model-a'],
  availableModels: ['model-a'],
  providerType: 'openai-like',
};

describe('ProviderConfig connection probe feedback', () => {
  it('names a timed-out probe and keeps the upstream reason visible', async () => {
    checkModelReachability.mockResolvedValue({
      reachable: false,
      latency_ms: null,
      error: 'No response within 15s',
      error_kind: 'timeout',
      cached: false,
    });
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <ProviderConfig
          provider={provider}
          onChange={vi.fn()}
          onValidateModel={vi.fn().mockResolvedValue({ success: true })}
          onToggleEnabled={vi.fn().mockResolvedValue(true)}
        />
      </TooltipProvider>,
    );

    await user.click(screen.getByRole('button', { name: '测试连接' }));

    await waitFor(() => expect(screen.getAllByText(/连接超时/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/No response within 15s/).length).toBeGreaterThan(0);
  });

  it('keeps the provider error reason visible instead of a generic message', async () => {
    checkModelReachability.mockResolvedValue({
      reachable: false,
      latency_ms: null,
      error: 'AuthenticationError: invalid api key',
      error_kind: 'provider_error',
      cached: false,
    });
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <ProviderConfig
          provider={provider}
          onChange={vi.fn()}
          onValidateModel={vi.fn().mockResolvedValue({ success: true })}
          onToggleEnabled={vi.fn().mockResolvedValue(true)}
        />
      </TooltipProvider>,
    );

    await user.click(screen.getByRole('button', { name: '测试连接' }));

    await waitFor(() => expect(screen.getAllByText(/不可达/).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/AuthenticationError: invalid api key/).length).toBeGreaterThan(0);
  });
});
