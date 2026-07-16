import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const mockCompleteOnboarding = vi.fn(() => Promise.resolve({ success: true, message: 'ok' }));
const mockDiscoverMigrationSources = vi.fn(() => Promise.resolve({ sources: [] }));
const mockProbeLocalCapabilities = vi.fn(() => Promise.resolve({ results: [], search: [] }));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => true,
  isTauriRuntime: () => false,
  getApiBaseUrl: () => '/api/v1',
  getBackendBaseUrl: () => 'http://localhost:8080',
  getDeployMode: () => 'local',
  isSandbox: () => false,
  isSandboxAuthBuild: () => false,
  shouldRedirectToLoginOnAuthFailure: () => false,
  getLocalUserId: () => 'test-user',
  resolveE2eApiBase: () => null,
  normalizeConfiguredBaseUrl: (v: string | null, f: string) => v || f,
  getDocsUrl: (p: string) => `https://docs.example.com${p}`,
}));

vi.mock('@/services/migrationDiscovery', () => ({
  discoverMigrationSources: (...args: unknown[]) => mockDiscoverMigrationSources(...args),
}));

vi.mock('@/services/localCapabilitiesProbe', () => ({
  probeLocalCapabilities: (...args: unknown[]) => mockProbeLocalCapabilities(...args),
  invalidateLocalCapabilitiesProbeCache: vi.fn(),
}));

vi.mock('@/services/onboarding', () => ({
  completeOnboarding: () => mockCompleteOnboarding(),
}));

vi.mock('@/components/features/app-shell/BrandLogo', () => ({
  default: () => <div data-testid="brand-logo" />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...rest}>{children}</button>
  ),
}));

vi.mock('@/components/features/settings/sections/knowledge/MigrationWizardSection', () => ({
  default: ({ onMigrationComplete }: { onMigrationComplete: () => void }) => (
    <div data-testid="migration-wizard">
      <button data-testid="migration-done" onClick={onMigrationComplete}>Done</button>
    </div>
  ),
}));

vi.mock('../LocalCapabilitiesSetup', () => ({
  default: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="local-capabilities">
      <button data-testid="capabilities-done" onClick={onComplete}>Done</button>
    </div>
  ),
}));

vi.mock('../SmartRoutingStep', () => ({
  default: ({ onComplete, onSkip }: { onComplete: () => void; onSkip: () => void }) => (
    <div data-testid="smart-routing-step">
      <button data-testid="routing-enable" onClick={onComplete}>Enable</button>
      <button data-testid="routing-skip" onClick={onSkip}>Skip</button>
    </div>
  ),
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

const mockHasEnabledProvider = vi.hoisted(() => ({ value: false }));
const mockIsInitialized = vi.hoisted(() => ({ value: true }));
const mockSearchConfigured = vi.hoisted(() => ({ value: false }));
const mockEnabledModels = vi.hoisted(() => ({ value: [] as Array<{ providerId: string; model: string }> }));
const mockRoutingEnabled = vi.hoisted(() => ({ value: false }));

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      providers: mockHasEnabledProvider.value
        ? [{ id: 'openai', isEnabled: true, apiKeys: [{ isActive: true, key: 'sk-x' }] }]
        : [],
      isInitialized: mockIsInitialized.value,
      defaultModelConfig: {
        baseModel: { primary: null },
        routingConfig: mockRoutingEnabled.value ? { enabled: true } : null,
      },
      getEnabledModels: () => mockEnabledModels.value,
    }),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      searchServiceConfigs: mockSearchConfigured.value ? [{ isActive: true }] : [],
    }),
}));

vi.mock('@/store/config/searchService', () => ({
  getActiveSearchServiceConfig: (configs: unknown[]) =>
    Array.isArray(configs) && configs.length > 0 ? configs[0] : null,
}));

import OnboardingWizard from '../OnboardingWizard';

describe('OnboardingWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockHasEnabledProvider.value = false;
    mockIsInitialized.value = true;
    mockSearchConfigured.value = false;
    mockEnabledModels.value = [];
    mockRoutingEnabled.value = false;
    mockDiscoverMigrationSources.mockImplementation(() => Promise.resolve({ sources: [] }));
    mockProbeLocalCapabilities.mockImplementation(() => Promise.resolve({ results: [], search: [] }));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('welcome phase', () => {
    it('shows welcome screen with brand logo on mount', () => {
      render(<OnboardingWizard onComplete={vi.fn()} />);
      expect(screen.getByTestId('brand-logo')).toBeInTheDocument();
      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.getByText('step.initServices')).toBeInTheDocument();
    });

    it('runs migration discovery and local probe in parallel on mount', () => {
      render(<OnboardingWizard onComplete={vi.fn()} />);
      expect(mockDiscoverMigrationSources).toHaveBeenCalledWith(false);
      expect(mockProbeLocalCapabilities).toHaveBeenCalledWith(false);
    });
  });

  describe('step routing', () => {
    it('routes to migration when sources exist', async () => {
      mockDiscoverMigrationSources.mockImplementation(() =>
        Promise.resolve({ sources: [{ type: 'chatgpt', path: '/tmp' }] }),
      );

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('migration-wizard')).toBeInTheDocument();
      });
    });

    it('routes to capabilities when no migration and no provider', async () => {
      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });
    });

    it('auto-finishes when provider and search are already ready', async () => {
      mockHasEnabledProvider.value = true;
      mockSearchConfigured.value = true;

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalled();
      });
    });
  });

  describe('step transitions', () => {
    it('transitions from migration to capabilities', async () => {
      mockDiscoverMigrationSources.mockImplementation(() =>
        Promise.resolve({ sources: [{ type: 'chatgpt', path: '/tmp' }] }),
      );

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('migration-wizard')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('migration-done'));

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });
    });
  });

  describe('error resilience', () => {
    it('handles migration discovery failure gracefully', async () => {
      mockDiscoverMigrationSources.mockImplementation(() => Promise.reject(new Error('fail')));

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });
    });
  });

  describe('smart routing step', () => {
    it('shows routing step after capabilities when ≥2 models and routing not enabled', async () => {
      mockEnabledModels.value = [
        { providerId: 'openai', model: 'gpt-4o-mini' },
        { providerId: 'openai', model: 'gpt-4o' },
      ];

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('capabilities-done'));

      await waitFor(() => {
        expect(screen.getByTestId('smart-routing-step')).toBeInTheDocument();
      });
    });

    it('skips routing step when routing already enabled', async () => {
      mockHasEnabledProvider.value = true;
      mockSearchConfigured.value = true;
      mockEnabledModels.value = [
        { providerId: 'openai', model: 'gpt-4o-mini' },
        { providerId: 'openai', model: 'gpt-4o' },
      ];
      mockRoutingEnabled.value = true;

      const onComplete = vi.fn();
      render(<OnboardingWizard onComplete={onComplete} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalled();
      });

      expect(screen.queryByTestId('smart-routing-step')).not.toBeInTheDocument();
    });

    it('skips routing step when less than 2 models', async () => {
      mockEnabledModels.value = [{ providerId: 'openai', model: 'gpt-4o' }];

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('capabilities-done'));

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalled();
      });

      expect(screen.queryByTestId('smart-routing-step')).not.toBeInTheDocument();
    });

    it('finishes after routing enable click', async () => {
      mockEnabledModels.value = [
        { providerId: 'openai', model: 'gpt-4o-mini' },
        { providerId: 'openai', model: 'gpt-4o' },
      ];

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('capabilities-done'));

      await waitFor(() => {
        expect(screen.getByTestId('smart-routing-step')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('routing-enable'));

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalled();
      });
    });

    it('finishes after routing skip click', async () => {
      mockEnabledModels.value = [
        { providerId: 'openai', model: 'gpt-4o-mini' },
        { providerId: 'openai', model: 'gpt-4o' },
      ];

      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('local-capabilities')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('capabilities-done'));

      await waitFor(() => {
        expect(screen.getByTestId('smart-routing-step')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTestId('routing-skip'));

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalled();
      });
    });
  });

  describe('timing', () => {
    it('respects minimum 2500ms welcome duration', async () => {
      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.queryByTestId('local-capabilities')).not.toBeInTheDocument();
    });
  });
});
