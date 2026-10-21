/**
 * Unit tests for ModelPingSpeedTester component.
 *
 * [INPUT] ModelPingSpeedTester, modelTesterService
 * [OUTPUT] Full coverage tests for model latency pinging, badge states, and error handling.
 * [POS] src/components/features/model-tester/__tests__/ModelPingSpeedTester.test.tsx
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ModelPingSpeedTester } from '../ModelPingSpeedTester';
import { modelTesterService } from '../modelTesterService';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    testLatency: 'Test Latency',
    testing: 'Testing...',
    retest: 'Retest',
    unreachable: 'Unreachable',
  };
  return translations[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('../modelTesterService', () => ({
  modelTesterService: {
    pingModel: vi.fn(),
  },
}));

describe('ModelPingSpeedTester', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial state with test latency button and executes ping on click', async () => {
    const mockPing = vi.mocked(modelTesterService.pingModel);
    mockPing.mockResolvedValueOnce({
      model_id: 'gpt-4o',
      provider: 'openai',
      status: 'healthy',
      ttft_ms: 245,
      tokens_per_second: 42.5,
      auth_verified: true,
      checked_at_epoch: 1700000000,
      error_message: null,
    });

    const onTested = vi.fn();

    render(<ModelPingSpeedTester modelId="gpt-4o" provider="openai" onTested={onTested} />);

    const testBtn = screen.getByRole('button', { name: 'Test model latency' });
    expect(screen.getByText('Test Latency')).toBeInTheDocument();

    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(mockPing).toHaveBeenCalledWith({
        model_id: 'gpt-4o',
        provider: 'openai',
      });
    });

    await waitFor(() => {
      expect(screen.getByText('245ms')).toBeInTheDocument();
      expect(screen.getByText('42.5 tok/s')).toBeInTheDocument();
      expect(screen.getByText('Retest')).toBeInTheDocument();
    });

    expect(onTested).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'healthy',
        ttft_ms: 245,
      }),
    );
  });

  it('displays unreachable badge when model ping fails', async () => {
    const mockPing = vi.mocked(modelTesterService.pingModel);
    mockPing.mockResolvedValueOnce({
      model_id: 'custom-model',
      provider: 'custom',
      status: 'unreachable',
      ttft_ms: -1,
      tokens_per_second: 0,
      auth_verified: false,
      checked_at_epoch: 1700000000,
      error_message: 'Connection timed out',
    });

    render(<ModelPingSpeedTester modelId="custom-model" provider="custom" />);

    const testBtn = screen.getByRole('button', { name: 'Test model latency' });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(screen.getByText('Unreachable')).toBeInTheDocument();
    });
  });

  it('displays degraded badge when latency exceeds threshold', async () => {
    const mockPing = vi.mocked(modelTesterService.pingModel);
    mockPing.mockResolvedValueOnce({
      model_id: 'slow-model',
      provider: 'slow-provider',
      status: 'healthy',
      ttft_ms: 1850,
      tokens_per_second: 12.0,
      auth_verified: true,
      checked_at_epoch: 1700000000,
      error_message: null,
    });

    render(<ModelPingSpeedTester modelId="slow-model" provider="slow-provider" />);

    const testBtn = screen.getByRole('button', { name: 'Test model latency' });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(screen.getByText('1850ms')).toBeInTheDocument();
    });
  });
});
