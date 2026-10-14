'use client';

import { act, render, screen, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('lucide-react', () => ({
  AlertCircle: (props: Record<string, unknown>) => <svg data-testid="alert-icon" {...props} />,
  Zap: (props: Record<string, unknown>) => <svg data-testid="zap-icon" {...props} />,
  ExternalLink: (props: Record<string, unknown>) => <svg data-testid="external-link-icon" {...props} />,
  Copy: (props: Record<string, unknown>) => <svg data-testid="copy-icon" {...props} />,
  Check: (props: Record<string, unknown>) => <svg data-testid="check-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader2-icon" {...props} />,
  X: (props: Record<string, unknown>) => <svg data-testid="x-icon" {...props} />,
  ShieldCheck: (props: Record<string, unknown>) => <svg data-testid="shield-check-icon" {...props} />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

const mockUseProviderStore = vi.fn();
vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: unknown) => unknown) => mockUseProviderStore(selector),
}));

const { mockStartXaiOAuth, mockPollXaiOAuth, mockConnectProviderSubscription, mockWriteToClipboard } = vi.hoisted(
  () => ({
    mockStartXaiOAuth: vi.fn(),
    mockPollXaiOAuth: vi.fn(),
    mockConnectProviderSubscription: vi.fn(),
    mockWriteToClipboard: vi.fn(),
  }),
);

vi.mock('@/lib/utils/clipboardUtils', () => ({ writeToClipboard: mockWriteToClipboard }));

vi.mock('@/services/xai-oauth', () => ({
  startXaiOAuth: mockStartXaiOAuth,
  pollXaiOAuth: mockPollXaiOAuth,
}));

vi.mock('@/store/config/providerSubscription', () => ({
  connectProviderSubscription: mockConnectProviderSubscription,
}));

import NoProviderBanner from '../NoProviderBanner';

describe('NoProviderBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when store is not initialized', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = { isInitialized: false, providers: [] };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when a provider is enabled with active API key', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: 'sk-xxx' }] }],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when ollama provider is enabled (no API key needed)', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'ollama', isEnabled: true, apiKeys: [] }],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when lm_studio provider is enabled', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'lm_studio', isEnabled: true, apiKeys: [] }],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });

  it('renders banner when initialized but no provider is enabled', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'openai', isEnabled: false, apiKeys: [] }],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    expect(screen.getByText('noProviderBanner')).toBeInTheDocument();
    expect(screen.getByText('noProviderAction')).toBeInTheDocument();
    expect(screen.getByTestId('alert-icon')).toBeInTheDocument();
  });

  it('renders banner when provider enabled but API key inactive', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'openai', isEnabled: true, apiKeys: [{ isActive: false, key: 'sk-xxx' }] }],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    expect(screen.getByText('noProviderBanner')).toBeInTheDocument();
  });

  it('renders banner when provider enabled but API key empty', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: '' }] }],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    expect(screen.getByText('noProviderBanner')).toBeInTheDocument();
  });

  it('navigates to /settings/models on button click', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [],
      };
      return selector(state);
    });

    render(<NoProviderBanner />);
    fireEvent.click(screen.getByText('noProviderAction'));
    expect(mockPush).toHaveBeenCalledWith('/settings/models');
  });

  it('renders quick subscription connect button and opens modal', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = { isInitialized: true, providers: [] };
      return selector(state);
    });

    render(<NoProviderBanner />);
    const quickBtn = screen.getByText('subscriptionQuickConnect');
    expect(quickBtn).toBeInTheDocument();
    fireEvent.click(quickBtn);

    expect(screen.getByText('subscriptionModalTitle')).toBeInTheDocument();
    expect(screen.getByText('subscriptionXai')).toBeInTheDocument();
    expect(screen.getAllByText('subscriptionConnectBtn')).toHaveLength(1);
  });

  it('closes modal when clicking cancel button', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = { isInitialized: true, providers: [] };
      return selector(state);
    });

    render(<NoProviderBanner />);
    const quickBtn = screen.getByText('subscriptionQuickConnect');
    fireEvent.click(quickBtn);

    expect(screen.getByText('subscriptionModalTitle')).toBeInTheDocument();
    const cancelBtn = screen.getByLabelText('close');
    fireEvent.click(cancelBtn);

    expect(screen.queryByText('subscriptionModalTitle')).not.toBeInTheDocument();
  });

  it('renders nothing when an oauthConnected provider is enabled', () => {
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state = {
        isInitialized: true,
        providers: [{ id: 'xai', isEnabled: true, apiKeys: [], oauthConnected: true }],
      };
      return selector(state);
    });

    const { container } = render(<NoProviderBanner />);
    expect(container.innerHTML).toBe('');
  });
});

const AUTHORIZATION = {
  user_code: 'ABCD-1234',
  verification_uri: 'https://x.ai/device',
  verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
  expires_in: 600,
  interval: 5,
};

describe('NoProviderBanner xAI subscription flow', () => {
  type StoreState = { isInitialized: boolean; providers: Array<Record<string, unknown>> };
  let storeState: StoreState;

  function mockStore(providers: StoreState['providers'] = []) {
    storeState = { isInitialized: true, providers };
    mockUseProviderStore.mockImplementation((selector: (s: StoreState) => unknown) => selector(storeState));
  }

  async function startFlow() {
    fireEvent.click(screen.getByText('subscriptionQuickConnect'));
    fireEvent.click(screen.getByText('subscriptionXai'));
    await act(async () => {});
  }

  async function advance(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockStartXaiOAuth.mockResolvedValue(AUTHORIZATION);
    mockPollXaiOAuth.mockResolvedValue({ status: 'pending' });
    mockConnectProviderSubscription.mockResolvedValue(undefined);
    mockStore();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the device code from the authorization and keeps polling with it until approval', async () => {
    render(<NoProviderBanner />);
    await startFlow();

    expect(mockStartXaiOAuth).toHaveBeenCalledOnce();
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
    expect(screen.getByText('subscriptionWaiting')).toBeInTheDocument();
    expect(mockPollXaiOAuth).not.toHaveBeenCalled();

    await advance(5000);
    expect(mockPollXaiOAuth).toHaveBeenCalledWith('ABCD-1234');
    await advance(5000);
    expect(mockPollXaiOAuth).toHaveBeenCalledTimes(2);
    expect(mockConnectProviderSubscription).not.toHaveBeenCalled();
  });

  it('describes the provider without naming models that will age', () => {
    render(<NoProviderBanner />);
    fireEvent.click(screen.getByText('subscriptionQuickConnect'));

    expect(screen.getByText('subscriptionXaiSummary')).toBeInTheDocument();
  });

  it('starts only one authorization however often the provider row is clicked', async () => {
    mockStartXaiOAuth.mockReturnValue(new Promise(() => {}));
    render(<NoProviderBanner />);
    fireEvent.click(screen.getByText('subscriptionQuickConnect'));

    const row = screen.getByText('subscriptionXai').closest('button') as HTMLButtonElement;
    fireEvent.click(row);
    await act(async () => {});
    fireEvent.click(row);

    expect(mockStartXaiOAuth).toHaveBeenCalledOnce();
    expect(row).toBeDisabled();
  });

  it('opens the pre-filled verification page', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<NoProviderBanner />);
    await startFlow();

    fireEvent.click(screen.getByText('subscriptionOpenAuth'));

    expect(openSpy).toHaveBeenCalledWith('https://x.ai/device?code=ABCD-1234', '_blank', 'noopener,noreferrer');
    openSpy.mockRestore();
  });

  it('copies the device code through the shared clipboard helper and confirms it briefly', async () => {
    mockWriteToClipboard.mockResolvedValue(true);
    render(<NoProviderBanner />);
    await startFlow();

    expect(screen.queryAllByTestId('check-icon')).toHaveLength(0);
    await act(async () => {
      fireEvent.click(screen.getByLabelText('subscriptionCopyCode'));
    });

    expect(mockWriteToClipboard).toHaveBeenCalledExactlyOnceWith('ABCD-1234', true);
    expect(screen.getAllByTestId('check-icon')).toHaveLength(1);
    expect(screen.getByLabelText('subscriptionCopied')).toBeInTheDocument();

    await advance(2000);
    expect(screen.queryAllByTestId('check-icon')).toHaveLength(0);
    expect(screen.getByLabelText('subscriptionCopyCode')).toBeInTheDocument();
  });

  it('does not confirm a copy the clipboard refused', async () => {
    mockWriteToClipboard.mockResolvedValue(false);
    render(<NoProviderBanner />);
    await startFlow();

    await act(async () => {
      fireEvent.click(screen.getByLabelText('subscriptionCopyCode'));
    });

    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
    expect(screen.queryAllByTestId('check-icon')).toHaveLength(0);
  });

  it('applies the connected subscription once approved, confirms it, then closes the dialog', async () => {
    mockPollXaiOAuth.mockResolvedValue({ status: 'success' });
    render(<NoProviderBanner />);
    await startFlow();

    await advance(5000);

    expect(mockConnectProviderSubscription).toHaveBeenCalledExactlyOnceWith('xai');
    expect(screen.getByText('subscriptionConnected')).toBeInTheDocument();

    await advance(1500);
    expect(screen.queryByText('subscriptionModalTitle')).not.toBeInTheDocument();
  });

  it('keeps the confirmation visible although the connection already hides the strip', async () => {
    mockPollXaiOAuth.mockResolvedValue({ status: 'success' });
    mockConnectProviderSubscription.mockImplementation(async () => {
      storeState.providers = [{ id: 'xai', isEnabled: true, apiKeys: [], oauthConnected: true }];
    });
    const { container } = render(<NoProviderBanner />);
    await startFlow();

    await advance(5000);

    expect(screen.queryByText('noProviderBanner')).not.toBeInTheDocument();
    expect(screen.getByText('subscriptionConnected')).toBeInTheDocument();

    await advance(1500);
    expect(container.innerHTML).toBe('');
  });

  it.each([
    ['expired', 'subscriptionFailedExpired'],
    ['denied', 'subscriptionFailedDenied'],
  ] as const)('explains a %s authorization in plain words and offers another attempt', async (status, messageKey) => {
    mockPollXaiOAuth.mockResolvedValue({ status, error: 'invalid_grant: raw server detail' });
    render(<NoProviderBanner />);
    await startFlow();

    await advance(5000);
    await advance(15000);

    expect(screen.getByRole('alert')).toHaveTextContent(messageKey);
    expect(screen.queryByText(/raw server detail/)).not.toBeInTheDocument();
    expect(screen.getByText('subscriptionConnectBtn')).toBeInTheDocument();
    expect(mockPollXaiOAuth).toHaveBeenCalledOnce();
    expect(mockConnectProviderSubscription).not.toHaveBeenCalled();
  });

  it('tells the user when the authorization times out', async () => {
    mockStartXaiOAuth.mockResolvedValue({
      user_code: 'ABCD-1234',
      verification_uri: 'https://x.ai/device',
      verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
      expires_in: 10,
      interval: 5,
    });
    render(<NoProviderBanner />);
    await startFlow();

    await advance(10000);

    expect(screen.getByRole('alert')).toHaveTextContent('subscriptionFailedTimeout');
    expect(screen.getByText('subscriptionConnectBtn')).toBeInTheDocument();
  });

  it('tells the user when the authorization cannot be started, and clears the message as soon as they retry', async () => {
    mockStartXaiOAuth.mockRejectedValueOnce(new Error('503 upstream detail'));
    render(<NoProviderBanner />);
    await startFlow();

    expect(screen.getByRole('alert')).toHaveTextContent('subscriptionFailedStart');
    expect(screen.queryByText(/upstream detail/)).not.toBeInTheDocument();

    let answer: (response: typeof AUTHORIZATION) => void = () => {};
    mockStartXaiOAuth.mockReturnValueOnce(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    fireEvent.click(screen.getByText('subscriptionXai'));

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    await act(async () => answer(AUTHORIZATION));
    expect(screen.getByText('ABCD-1234')).toBeInTheDocument();
  });

  it('forgets the failure when the dialog is closed', async () => {
    mockStartXaiOAuth.mockRejectedValueOnce(new Error('503'));
    render(<NoProviderBanner />);
    await startFlow();
    expect(screen.getByRole('alert')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('close'));
    fireEvent.click(screen.getByText('subscriptionQuickConnect'));

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('stops polling when the dialog is closed', async () => {
    render(<NoProviderBanner />);
    await startFlow();

    fireEvent.click(screen.getByLabelText('close'));
    await advance(20000);

    expect(mockPollXaiOAuth).not.toHaveBeenCalled();
  });

  it('stops polling when the banner unmounts', async () => {
    const { unmount } = render(<NoProviderBanner />);
    await startFlow();

    unmount();
    await advance(20000);

    expect(mockPollXaiOAuth).not.toHaveBeenCalled();
  });
});
