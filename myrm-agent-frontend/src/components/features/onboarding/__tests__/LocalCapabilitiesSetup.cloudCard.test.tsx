'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const mockPush = vi.fn();
const mockCompleteOnboarding = vi.fn(() => Promise.resolve());
const mockUpdateProvider = vi.fn();
const mockSetBaseModel = vi.fn();
const mockSetLiteModel = vi.fn();
const mockAddProvider = vi.fn();
const mockDiscoverModelsFromEndpoint = vi.fn();
const mockCheckModelReachability = vi.fn();
let mockProviders: Array<Record<string, unknown>> = [];

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/services/onboarding', () => ({
  completeOnboarding: () => mockCompleteOnboarding(),
}));

vi.mock('@/services/localCapabilitiesProbe', () => ({
  invalidateLocalCapabilitiesProbeCache: vi.fn(),
}));

vi.mock('@/services/searxngSetup', () => ({
  startLocalSearxngAndRefreshProbe: vi.fn(),
}));

vi.mock('@/store/config/quickSearchSetup', () => ({
  buildQuickSearchConfig: vi.fn(),
}));

vi.mock('@/store/config/searchService', () => ({
  getActiveSearchServiceConfig: vi.fn(() => null),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconArrowRight: (props: Record<string, unknown>) => <svg data-testid="icon-arrow" {...props} />,
  IconCheck: (props: Record<string, unknown>) => <svg data-testid="icon-check" {...props} />,
  IconCpu: (props: Record<string, unknown>) => <svg data-testid="icon-cpu" {...props} />,
  IconGlobe: (props: Record<string, unknown>) => <svg data-testid="icon-globe" {...props} />,
  IconLoader: (props: Record<string, unknown>) => <svg data-testid="icon-loader" {...props} />,
  IconZap: (props: Record<string, unknown>) => <svg data-testid="icon-zap" {...props} />,
}));

vi.mock('@/components/features/settings/SearxngInstallConsentDialog', () => ({
  default: () => null,
}));

vi.mock('@/components/features/settings/model-service/HardwareCookbook', () => ({
  default: () => <div data-testid="hardware-cookbook" />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

vi.mock('@/store/useProviderStore', () => ({
  default: Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) =>
      selector({
        providers: mockProviders,
        addProvider: mockAddProvider,
        updateProvider: mockUpdateProvider,
        setBaseModel: mockSetBaseModel,
        setLiteModel: mockSetLiteModel,
      }),
    {
      getState: () => ({ providers: mockProviders }),
    },
  ),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      searchServiceConfigs: [],
      addSearchServiceConfig: vi.fn(),
    }),
}));

vi.mock('@/services/llm-config', () => ({
  discoverModelsFromEndpoint: (...args: unknown[]) => mockDiscoverModelsFromEndpoint(...args),
  checkModelReachability: (...args: unknown[]) => mockCheckModelReachability(...args),
}));

import LocalCapabilitiesSetup from '../LocalCapabilitiesSetup';

const NO_MODEL_PROBE = { results: [], search: [] };

const WITH_MODEL_PROBE = {
  results: [
    { provider: 'ollama', available: true, base_url: 'http://localhost:11434', models: ['llama3'] },
  ],
  recommended_model: 'llama3',
  search: [],
};

describe('LocalCapabilitiesSetup – Cloud Quick Start Card', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProviders = [
      {
        id: 'local_openai_compatible',
        providerType: 'openai-like',
        apiUrl: 'http://127.0.0.1:8899/v1',
        isEnabled: false,
        apiKeys: [],
        enabledModels: [],
        availableModels: [],
      },
    ];
  });

  it('renders cloud card when no provider enabled and no local model available', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    expect(screen.getByText('onboarding.cloudQuickStart')).toBeInTheDocument();
    expect(screen.getByText('onboarding.cloudQuickStartHint')).toBeInTheDocument();
  });

  it('renders exactly 3 cloud provider buttons', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    const arrows = screen.getAllByTestId('icon-arrow');
    expect(arrows).toHaveLength(3);
  });

  it('renders Gemini, SiliconFlow, OpenRouter provider names', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    expect(screen.getByText('onboarding.cloudProviderGemini')).toBeInTheDocument();
    expect(screen.getByText('onboarding.cloudProviderSiliconFlow')).toBeInTheDocument();
    expect(screen.getByText('onboarding.cloudProviderOpenRouter')).toBeInTheDocument();
  });

  it('renders provider hint texts', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    expect(screen.getByText('onboarding.cloudProviderGeminiHint')).toBeInTheDocument();
    expect(screen.getByText('onboarding.cloudProviderSiliconFlowHint')).toBeInTheDocument();
    expect(screen.getByText('onboarding.cloudProviderOpenRouterHint')).toBeInTheDocument();
  });

  it('navigates to /settings/models and calls completeOnboarding on cloud card click', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    fireEvent.click(screen.getByText('onboarding.cloudProviderGemini'));
    expect(mockPush).toHaveBeenCalledWith('/settings/models');
    expect(mockCompleteOnboarding).toHaveBeenCalledTimes(1);
  });

  it('does NOT render cloud card when local model is available', () => {
    render(<LocalCapabilitiesSetup probeResult={WITH_MODEL_PROBE} onComplete={vi.fn()} />);
    expect(screen.queryByText('onboarding.cloudQuickStart')).toBeNull();
  });

  it('renders IconZap in cloud card header', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    expect(screen.getByTestId('icon-zap')).toBeInTheDocument();
  });

  it('shows "configureLater" button when no model available', () => {
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);
    expect(screen.getByText('onboarding.configureLater')).toBeInTheDocument();
  });

  it('calls onComplete when "enterWorkspace" button clicked', () => {
    const onComplete = vi.fn();
    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={onComplete} />);
    fireEvent.click(screen.getByText('onboarding.enterWorkspace'));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('does not activate custom endpoint when reachability check fails', async () => {
    mockDiscoverModelsFromEndpoint.mockResolvedValue({
      success: true,
      normalized_api_url: 'http://127.0.0.1:8899/v1',
      models_url: 'http://127.0.0.1:8899/v1/models',
      models: ['qwen3:8b'],
      no_auth_local: true,
      error: null,
    });
    mockCheckModelReachability.mockResolvedValue({
      reachable: false,
      latency_ms: null,
      error: 'Health check returned no response',
      cached: false,
    });

    render(<LocalCapabilitiesSetup probeResult={NO_MODEL_PROBE} onComplete={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText('customApiUrlPlaceholder'), {
      target: { value: 'http://127.0.0.1:8899/v1' },
    });
    fireEvent.click(screen.getByText('customDetectModels'));

    await waitFor(() => {
      expect(mockDiscoverModelsFromEndpoint).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(await screen.findByText('customUseModel'));

    await waitFor(() => {
      expect(mockCheckModelReachability).toHaveBeenCalledTimes(1);
    });
    expect(mockUpdateProvider).not.toHaveBeenCalled();
    expect(screen.getByText('Health check returned no response')).toBeInTheDocument();
  });
});
