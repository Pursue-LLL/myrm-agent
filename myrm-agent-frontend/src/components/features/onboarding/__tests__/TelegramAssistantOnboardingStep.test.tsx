/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const mockApplyTelegramAssistantOnboarding = vi.fn();

const stableT = (key: string, values?: Record<string, string>) => {
  if (!values) {
    return key;
  }
  return `${key}:${Object.values(values).join(',')}`;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
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

const deployMode = vi.hoisted(() => ({ sandbox: false }));

vi.mock('@/lib/deploy-mode', () => ({
  isSandbox: () => deployMode.sandbox,
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
    deployMode.sandbox = false;
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
    mockApplyTelegramAssistantOnboarding.mockRejectedValueOnce(conflictError).mockRejectedValueOnce(conflictError);

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

  it.each([
    ['TELEGRAM_TOKEN_REJECTED', 'tokenRejectedError'],
    ['TELEGRAM_UNREACHABLE', 'telegramUnreachableError'],
  ])('explains a %s failure in the user language and does not retry', async (detailCode, messageKey) => {
    mockApplyTelegramAssistantOnboarding.mockRejectedValueOnce(
      Object.assign(new ApiError('English detail from the server', 400, [], undefined, detailCode), {
        data: { code: detailCode },
      }),
    );

    render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    await waitFor(() => {
      expect(screen.getByText(messageKey)).toBeInTheDocument();
    });
    expect(screen.queryByText('English detail from the server')).not.toBeInTheDocument();
    expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith(messageKey);
    expect(toast.error).not.toHaveBeenCalledWith('setupFailedToast');
  });

  it('does not send a sandbox user to a proxy setting the sandbox does not have', async () => {
    deployMode.sandbox = true;
    mockApplyTelegramAssistantOnboarding.mockRejectedValueOnce(
      Object.assign(new ApiError('English detail from the server', 400, [], undefined, 'TELEGRAM_UNREACHABLE'), {
        data: { code: 'TELEGRAM_UNREACHABLE' },
      }),
    );

    render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    expect(await screen.findByText('telegramUnreachableSandboxError')).toBeInTheDocument();
    expect(screen.queryByText('telegramUnreachableError')).not.toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('telegramUnreachableSandboxError');
  });

  it('keeps the generic toast for a failure the server did not classify', async () => {
    mockApplyTelegramAssistantOnboarding.mockRejectedValueOnce(new ApiError('Disk full', 500));

    render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('tokenLabel'), {
      target: { value: '1234567890:VALID_TOKEN' },
    });
    fireEvent.click(screen.getByText('setupButton'));

    expect(await screen.findByText('Disk full')).toBeInTheDocument();
    expect(toast.error).toHaveBeenCalledWith('setupFailedToast');
  });

  describe('proxy offer', () => {
    const connected = {
      success: true,
      message: 'ok',
      botUsername: 'myrm_bot',
      agentId: 'agent-1',
      agentName: 'Assistant',
      channelEnabled: true,
      connected: true,
      status: 'running',
    };

    function rejectOnce(detailCode: string, extra: Record<string, unknown> = {}) {
      mockApplyTelegramAssistantOnboarding.mockRejectedValueOnce(
        Object.assign(new ApiError('English detail from the server', 400, [], undefined, detailCode), {
          data: { code: detailCode, ...extra },
        }),
      );
    }

    function submitToken() {
      fireEvent.change(screen.getByLabelText('tokenLabel'), { target: { value: '1234567890:VALID_TOKEN' } });
      fireEvent.click(screen.getByText('setupButton'));
    }

    it('offers no proxy input before a failure and sends no proxy on the first try', async () => {
      mockApplyTelegramAssistantOnboarding.mockResolvedValueOnce(connected);

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);

      expect(screen.queryByLabelText('telegramProxy')).not.toBeInTheDocument();
      submitToken();

      await waitFor(() => expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(1));
      expect(mockApplyTelegramAssistantOnboarding.mock.calls[0][0]).toEqual(
        expect.objectContaining({ proxy: undefined }),
      );
    });

    it('offers the proxy input once Telegram is unreachable and sends the typed proxy on retry', async () => {
      const onComplete = vi.fn();
      rejectOnce('TELEGRAM_UNREACHABLE');
      mockApplyTelegramAssistantOnboarding.mockResolvedValueOnce(connected);

      render(<TelegramAssistantOnboardingStep onComplete={onComplete} onSkip={vi.fn()} />);
      submitToken();

      const proxyInput = await screen.findByLabelText('telegramProxy');
      fireEvent.change(proxyInput, { target: { value: '  socks5://127.0.0.1:1080  ' } });
      fireEvent.click(screen.getByText('setupButton'));

      await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
      expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(2);
      expect(mockApplyTelegramAssistantOnboarding.mock.calls[1][0]).toEqual(
        expect.objectContaining({ botToken: '1234567890:VALID_TOKEN', proxy: 'socks5://127.0.0.1:1080' }),
      );
    });

    it('sends no proxy when the offered input is left blank', async () => {
      rejectOnce('TELEGRAM_UNREACHABLE');
      mockApplyTelegramAssistantOnboarding.mockResolvedValueOnce(connected);

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();
      await screen.findByLabelText('telegramProxy');
      fireEvent.click(screen.getByText('setupButton'));

      await waitFor(() => expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(2));
      expect(mockApplyTelegramAssistantOnboarding.mock.calls[1][0]).toEqual(
        expect.objectContaining({ proxy: undefined }),
      );
    });

    it('flags a malformed proxy inline and holds the request back', async () => {
      rejectOnce('TELEGRAM_UNREACHABLE');

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();
      fireEvent.change(await screen.findByLabelText('telegramProxy'), { target: { value: '127.0.0.1:1080' } });

      expect(screen.getByText('telegramProxyInvalid')).toBeInTheDocument();
      expect(screen.getByText('setupButton').closest('button')).toBeDisabled();
      expect(mockApplyTelegramAssistantOnboarding).toHaveBeenCalledTimes(1);
    });

    it.each(['TELEGRAM_TOKEN_REJECTED', 'TELEGRAM_PROXY_REJECTED'])(
      'does not offer the proxy input after a %s failure',
      async (detailCode) => {
        rejectOnce(detailCode);

        render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
        submitToken();

        await waitFor(() => expect(toast.error).toHaveBeenCalled());
        expect(screen.queryByLabelText('telegramProxy')).not.toBeInTheDocument();
      },
    );

    it('keeps the proxy input out of the sandbox, which has no proxy to set', async () => {
      deployMode.sandbox = true;
      rejectOnce('TELEGRAM_UNREACHABLE');

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();

      await screen.findByText('telegramUnreachableSandboxError');
      expect(screen.queryByLabelText('telegramProxy')).not.toBeInTheDocument();
    });

    it('stops telling the user to enter a proxy once the failed attempt already went through one', async () => {
      rejectOnce('TELEGRAM_UNREACHABLE', { viaProxy: true });

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();

      expect(await screen.findByText('telegramUnreachableViaProxyError')).toBeInTheDocument();
      expect(screen.queryByText('telegramUnreachableError')).not.toBeInTheDocument();
      expect(toast.error).toHaveBeenCalledWith('telegramUnreachableViaProxyError');
      expect(screen.getByLabelText('telegramProxy')).toBeInTheDocument();
    });

    it('keeps asking for a proxy when the failed attempt used none', async () => {
      rejectOnce('TELEGRAM_UNREACHABLE', { viaProxy: false });

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();

      expect(await screen.findByText('telegramUnreachableError')).toBeInTheDocument();
      expect(screen.queryByText('telegramUnreachableViaProxyError')).not.toBeInTheDocument();
    });

    it('keeps the sandbox wording even if a proxy flag comes back, since the sandbox has no proxy to blame', async () => {
      deployMode.sandbox = true;
      rejectOnce('TELEGRAM_UNREACHABLE', { viaProxy: true });

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();

      expect(await screen.findByText('telegramUnreachableSandboxError')).toBeInTheDocument();
      expect(screen.queryByText('telegramUnreachableViaProxyError')).not.toBeInTheDocument();
    });

    it('explains a refused proxy address in the user language', async () => {
      rejectOnce('TELEGRAM_PROXY_REJECTED');

      render(<TelegramAssistantOnboardingStep onComplete={vi.fn()} onSkip={vi.fn()} />);
      submitToken();

      expect(await screen.findByText('proxyRejectedError')).toBeInTheDocument();
      expect(screen.queryByText('English detail from the server')).not.toBeInTheDocument();
      expect(toast.error).toHaveBeenCalledWith('proxyRejectedError');
    });
  });
});
