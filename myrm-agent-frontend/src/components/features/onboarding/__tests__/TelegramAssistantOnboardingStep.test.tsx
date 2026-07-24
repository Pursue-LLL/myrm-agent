/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockApplyTelegramAssistantOnboarding = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    if (!values) return key;
    return `${key}:${Object.values(values).join(',')}`;
  },
}));

vi.mock('@/lib/api', () => {
  class MockApiError extends Error {
    public data?: Record<string, unknown>;

    constructor(
      message: string,
      public code: number = 500,
      _details: Array<{ field?: string; issue: string }> = [],
      _traceId?: string,
      public businessCode?: string,
    ) {
      super(message);
      this.name = 'ApiError';
    }
  }

  return { ApiError: MockApiError };
});

vi.mock('@/lib/deploy-mode', () => ({
  isSandbox: () => false,
}));

vi.mock('@/services/onboarding', () => ({
  applyTelegramAssistantOnboarding: (...args: unknown[]) => mockApplyTelegramAssistantOnboarding(...args),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { toast } from 'sonner';
import { ApiError } from '@/lib/api';
import TelegramAssistantOnboardingStep from '../TelegramAssistantOnboardingStep';

describe('TelegramAssistantOnboardingStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('completes onboarding immediately when Telegram is connected', async () => {
    const onComplete = vi.fn();
    mockApplyTelegramAssistantOnboarding.mockResolvedValue({
      success: true,
      message: 'ok',
      botUsername: 'myrm_bot',
      agentId: 'agent-1',
      agentName: 'Assistant',
      channelEnabled: true,
      connected: true,
      status: 'running',
    });

    render(<TelegramAssistantOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.info).not.toHaveBeenCalled();
  });

  it('shows pending state when connected=false and allows continue', async () => {
    const onComplete = vi.fn();
    mockApplyTelegramAssistantOnboarding.mockResolvedValue({
      success: true,
      message: 'pending',
      botUsername: 'myrm_bot',
      agentId: 'agent-1',
      agentName: 'Assistant',
      channelEnabled: true,
      connected: false,
      status: 'starting',
    });

    render(<TelegramAssistantOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    await waitFor(() => {
      expect(screen.getByText('pendingTitle')).toBeInTheDocument();
    });

    expect(onComplete).not.toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalledTimes(1);
    expect(screen.getByText('retryButton')).toBeInTheDocument();

    fireEvent.click(screen.getByText('continueButton'));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('retries once when onboarding is already in progress', async () => {
    const onComplete = vi.fn();
    mockApplyTelegramAssistantOnboarding
      .mockRejectedValueOnce(
        Object.assign(
          new ApiError(
            'Telegram onboarding is already in progress. Please retry shortly.',
            409,
            [],
            undefined,
            'TELEGRAM_ONBOARDING_IN_PROGRESS',
          ),
          { data: { code: 'TELEGRAM_ONBOARDING_IN_PROGRESS' } },
        ),
      )
      .mockResolvedValueOnce({
        success: true,
        message: 'ok',
        botUsername: 'myrm_bot',
        agentId: 'agent-1',
        agentName: 'Assistant',
        channelEnabled: true,
        connected: true,
        status: 'running',
      });

    render(<TelegramAssistantOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
    expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(2);
    expect(toast.info).toHaveBeenCalledWith('retryingToast');
  });

  it('shows friendly error when onboarding conflict persists', async () => {
    const onComplete = vi.fn();
    const conflictError = Object.assign(
      new ApiError(
        'Telegram onboarding is already in progress. Please retry shortly.',
        409,
        [],
        undefined,
        'TELEGRAM_ONBOARDING_IN_PROGRESS',
      ),
      { data: { code: 'TELEGRAM_ONBOARDING_IN_PROGRESS' } },
    );
    mockApplyTelegramAssistantOnboarding
      .mockRejectedValueOnce(conflictError)
      .mockRejectedValueOnce(conflictError);

    render(<TelegramAssistantOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    await waitFor(() => {
      expect(screen.getByText('inProgressFriendlyError')).toBeInTheDocument();
    });
    expect(onComplete).not.toHaveBeenCalled();
    expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(2);
  });
});
