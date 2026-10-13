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

const { mockStartXaiOAuth, mockPollXaiOAuth } = vi.hoisted(() => ({
  mockStartXaiOAuth: vi.fn(),
  mockPollXaiOAuth: vi.fn(),
}));

vi.mock('@/services/xai-oauth', () => ({
  startXaiOAuth: mockStartXaiOAuth,
  pollXaiOAuth: mockPollXaiOAuth,
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
    const cancelBtn = screen.getByLabelText('Close');
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

describe('NoProviderBanner xAI subscription flow', () => {
  const mockUpdateProvider = vi.fn();
  const mockSetBaseModel = vi.fn();

  function mockStore(overrides: Record<string, unknown> = {}) {
    const state = {
      isInitialized: true,
      providers: [],
      updateProvider: mockUpdateProvider,
      setBaseModel: mockSetBaseModel,
      defaultModelConfig: { baseModel: null },
      ...overrides,
    };
    mockUseProviderStore.mockImplementation((selector: (s: Record<string, unknown>) => unknown) => selector(state));
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
    mockStartXaiOAuth.mockResolvedValue({
      user_code: 'ABCD-1234',
      verification_uri: 'https://x.ai/device',
      verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
      expires_in: 600,
      interval: 5,
    });
    mockPollXaiOAuth.mockResolvedValue({ status: 'pending' });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the device code from the authorization and keeps polling with it until approval', async () => {
    mockStore();
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
    expect(mockUpdateProvider).not.toHaveBeenCalled();
  });

  it('opens the pre-filled verification page', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    mockStore();
    render(<NoProviderBanner />);
    await startFlow();

    fireEvent.click(screen.getByText('subscriptionOpenAuth'));

    expect(openSpy).toHaveBeenCalledWith('https://x.ai/device?code=ABCD-1234', '_blank');
    openSpy.mockRestore();
  });

  it('enables xAI with its default models and binds the base model once approved, then closes the dialog', async () => {
    mockPollXaiOAuth.mockResolvedValue({ status: 'success' });
    mockStore();
    render(<NoProviderBanner />);
    await startFlow();

    await advance(5000);

    expect(mockUpdateProvider).toHaveBeenCalledWith('xai', {
      isEnabled: true,
      oauthConnected: true,
      availableModels: ['grok-2', 'grok-2-mini', 'grok-beta'],
      enabledModels: ['grok-2'],
    });
    expect(mockSetBaseModel).toHaveBeenCalledWith({ providerId: 'xai', model: 'grok-2' });
    expect(screen.getByText('subscriptionConnected')).toBeInTheDocument();

    await advance(1500);
    expect(screen.queryByText('subscriptionModalTitle')).not.toBeInTheDocument();
  });

  it('keeps the models the provider already had and an existing base model', async () => {
    mockPollXaiOAuth.mockResolvedValue({ status: 'success' });
    mockStore({
      providers: [
        {
          id: 'xai',
          isEnabled: false,
          apiKeys: [],
          availableModels: ['grok-3', 'grok-2'],
          enabledModels: ['grok-3'],
        },
      ],
      defaultModelConfig: { baseModel: { primary: 'gpt-4o', providerId: 'openai' } },
    });
    render(<NoProviderBanner />);
    await startFlow();

    await advance(5000);

    expect(mockUpdateProvider).toHaveBeenCalledWith('xai', {
      isEnabled: true,
      oauthConnected: true,
      availableModels: ['grok-3', 'grok-2', 'grok-2-mini', 'grok-beta'],
      enabledModels: ['grok-3', 'grok-2'],
    });
    expect(mockSetBaseModel).not.toHaveBeenCalled();
  });

  it.each(['expired', 'denied'])(
    'stops polling and leaves the provider untouched when the authorization is %s',
    async (status) => {
      mockPollXaiOAuth.mockResolvedValue({ status });
      mockStore();
      render(<NoProviderBanner />);
      await startFlow();

      await advance(5000);
      await advance(15000);

      expect(mockPollXaiOAuth).toHaveBeenCalledOnce();
      expect(mockUpdateProvider).not.toHaveBeenCalled();
      expect(mockSetBaseModel).not.toHaveBeenCalled();
    },
  );

  it('stops polling when the dialog is closed', async () => {
    mockStore();
    render(<NoProviderBanner />);
    await startFlow();

    fireEvent.click(screen.getByLabelText('Close'));
    await advance(20000);

    expect(mockPollXaiOAuth).not.toHaveBeenCalled();
  });

  it('stops polling when the banner unmounts', async () => {
    mockStore();
    const { unmount } = render(<NoProviderBanner />);
    await startFlow();

    unmount();
    await advance(20000);

    expect(mockPollXaiOAuth).not.toHaveBeenCalled();
  });
});
