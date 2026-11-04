import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const mockCompleteOnboarding = vi.fn(() => Promise.resolve({ success: true, message: 'ok' }));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/onboarding', () => ({
  completeOnboarding: () => mockCompleteOnboarding(),
}));

vi.mock('@/components/features/app-shell/BrandLogo', () => ({
  default: () => <div data-testid="brand-logo" />,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...rest}>
      {children}
    </button>
  ),
}));

vi.mock('@/components/features/settings/sections/knowledge/MigrationWizardSection', () => ({
  default: ({ onMigrationComplete }: { onMigrationComplete: () => void }) => (
    <div data-testid="migration-wizard">
      <button data-testid="migration-done" onClick={onMigrationComplete}>
        Done
      </button>
    </div>
  ),
}));

vi.mock('@/components/features/instance-archive/RestoreEntry', () => ({
  RestoreEntry: () => <div data-testid="restore-entry" />,
}));

vi.mock('../FirstRunDoctorCard', () => ({
  default: () => <div data-testid="doctor-card" />,
}));

function stepMock(testId: string, completeId: string, skipId: string) {
  return {
    default: ({ onComplete, onSkip }: { onComplete: () => void; onSkip: () => void }) => (
      <div data-testid={testId}>
        <button data-testid={completeId} onClick={onComplete}>
          Done
        </button>
        <button data-testid={skipId} onClick={onSkip}>
          Skip
        </button>
      </div>
    ),
  };
}

vi.mock('../ToolsConnectOnboardingStep', () =>
  stepMock('tools-connect-step', 'tools-connect-done', 'tools-connect-skip'),
);
vi.mock('../SmartRoutingStep', () => stepMock('smart-routing-step', 'routing-enable', 'routing-skip'));
vi.mock('../SmartGuardStep', () => stepMock('smart-guard-step', 'guard-enable', 'guard-skip'));
vi.mock('../ThemeOnboardingStep', () => stepMock('theme-onboarding-step', 'theme-continue', 'theme-skip'));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}));

const mockIsInitialized = vi.hoisted(() => ({ value: true }));
const mockEnabledModels = vi.hoisted(() => ({ value: [] as Array<{ providerId: string; model: string }> }));
const mockRoutingEnabled = vi.hoisted(() => ({ value: false }));
const mockSecurityConfig = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }));

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      isInitialized: mockIsInitialized.value,
      defaultModelConfig: {
        baseModel: { primary: null },
        routingConfig: mockRoutingEnabled.value ? { enabled: true } : null,
      },
      getEnabledModels: () => mockEnabledModels.value,
    }),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: (key: string) => (key === 'securityConfig' ? mockSecurityConfig.value : null),
  }),
}));

vi.mock('@/services/config/types', () => ({}));

import OnboardingWizard from '../OnboardingWizard';

const TWO_MODELS = [
  { providerId: 'openai', model: 'gpt-4o-mini' },
  { providerId: 'openai', model: 'gpt-4o' },
];

async function renderPastWelcome(onComplete: () => void = vi.fn()) {
  render(<OnboardingWizard onComplete={onComplete} />);
  await act(async () => {
    vi.advanceTimersByTime(3000);
  });
}

async function clickWhenShown(testId: string) {
  await waitFor(() => {
    expect(screen.getByTestId(testId)).toBeInTheDocument();
  });
  fireEvent.click(screen.getByTestId(testId));
}

/** Walks migration -> tools connect -> health; the next screen is whatever the store state selects. */
async function passMigrationToolsAndHealth() {
  await clickWhenShown('migration-done');
  await clickWhenShown('tools-connect-skip');
  await waitFor(() => {
    expect(screen.getByText('onboarding.doctorContinueButton')).toBeInTheDocument();
  });
  fireEvent.click(screen.getByText('onboarding.doctorContinueButton'));
}

describe('OnboardingWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockIsInitialized.value = true;
    mockEnabledModels.value = [];
    mockRoutingEnabled.value = false;
    mockSecurityConfig.value = null;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('welcome phase', () => {
    it('shows the brand welcome screen on mount', () => {
      render(<OnboardingWizard onComplete={vi.fn()} />);
      expect(screen.getByTestId('brand-logo')).toBeInTheDocument();
      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.getByText('step.initServices')).toBeInTheDocument();
    });

    it('holds the welcome screen for the minimum duration', async () => {
      render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(1000);
      });

      expect(screen.getByText('title')).toBeInTheDocument();
      expect(screen.queryByTestId('migration-wizard')).not.toBeInTheDocument();
    });

    it('keeps waiting after the minimum duration until the provider store is initialized', async () => {
      mockIsInitialized.value = false;
      const { rerender } = render(<OnboardingWizard onComplete={vi.fn()} />);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });
      expect(screen.queryByTestId('migration-wizard')).not.toBeInTheDocument();

      mockIsInitialized.value = true;
      rerender(<OnboardingWizard onComplete={vi.fn()} />);

      await waitFor(() => {
        expect(screen.getByTestId('migration-wizard')).toBeInTheDocument();
      });
    });
  });

  describe('migration step', () => {
    it('opens on the migration step and offers restore from a backup there', async () => {
      await renderPastWelcome();

      await waitFor(() => {
        expect(screen.getByTestId('migration-wizard')).toBeInTheDocument();
      });
      expect(screen.getByTestId('restore-entry')).toBeInTheDocument();
      expect(screen.getByText('onboarding.instantStartButton')).toBeInTheDocument();
    });

    it('moves on to tools connect when the migration finishes', async () => {
      await renderPastWelcome();
      await clickWhenShown('migration-done');
      await waitFor(() => {
        expect(screen.getByTestId('tools-connect-step')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('restore-entry')).not.toBeInTheDocument();
    });

    it('moves on to tools connect from the skip button', async () => {
      await renderPastWelcome();
      await waitFor(() => {
        expect(screen.getByTestId('migration-wizard')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('onboarding.skipStep'));
      await waitFor(() => {
        expect(screen.getByTestId('tools-connect-step')).toBeInTheDocument();
      });
    });

    it('finishes straight away from the instant start button', async () => {
      const onComplete = vi.fn();
      await renderPastWelcome(onComplete);

      await waitFor(() => {
        expect(screen.getByText('onboarding.instantStartButton')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('onboarding.instantStartButton'));

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalledTimes(1);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      expect(onComplete).toHaveBeenCalledTimes(1);
    });

    it('still lets the user in when saving the completion fails', async () => {
      mockCompleteOnboarding.mockRejectedValueOnce(new Error('offline'));
      const onComplete = vi.fn();
      await renderPastWelcome(onComplete);

      await waitFor(() => {
        expect(screen.getByText('onboarding.instantStartButton')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('onboarding.instantStartButton'));

      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
  });

  describe('health step', () => {
    it('shows the doctor card and can be skipped', async () => {
      await renderPastWelcome();
      await clickWhenShown('migration-done');
      await clickWhenShown('tools-connect-skip');

      await waitFor(() => {
        expect(screen.getByTestId('doctor-card')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('onboarding.skipStep'));

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
    });
  });

  describe('smart routing step', () => {
    it('is offered with two or more enabled models while routing is off', async () => {
      mockEnabledModels.value = TWO_MODELS;
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await waitFor(() => {
        expect(screen.getByTestId('smart-routing-step')).toBeInTheDocument();
      });
    });

    it('is skipped when routing is already enabled', async () => {
      mockEnabledModels.value = TWO_MODELS;
      mockRoutingEnabled.value = true;
      mockSecurityConfig.value = { autoReviewEnabled: true };
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('smart-routing-step')).not.toBeInTheDocument();
    });

    it('is skipped with fewer than two enabled models', async () => {
      mockEnabledModels.value = [{ providerId: 'openai', model: 'gpt-4o' }];
      mockSecurityConfig.value = { autoReviewEnabled: true };
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('smart-routing-step')).not.toBeInTheDocument();
    });

    it.each([['routing-enable'], ['routing-skip']])('leads to the next step after %s', async (buttonId) => {
      mockEnabledModels.value = TWO_MODELS;
      mockSecurityConfig.value = { autoReviewEnabled: true };
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await clickWhenShown(buttonId);

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
    });
  });

  describe('smart guard step', () => {
    beforeEach(() => {
      mockEnabledModels.value = [{ providerId: 'openai', model: 'gpt-4o' }];
      mockRoutingEnabled.value = true;
    });

    it('is offered while auto review is off', async () => {
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await waitFor(() => {
        expect(screen.getByTestId('smart-guard-step')).toBeInTheDocument();
      });
    });

    it('is skipped when auto review is already on', async () => {
      mockSecurityConfig.value = { autoReviewEnabled: true };
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('smart-guard-step')).not.toBeInTheDocument();
    });

    it('is skipped when no model is enabled', async () => {
      mockEnabledModels.value = [];
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
      expect(screen.queryByTestId('smart-guard-step')).not.toBeInTheDocument();
    });

    it('follows smart routing when both apply', async () => {
      mockRoutingEnabled.value = false;
      mockEnabledModels.value = [
        { providerId: 'deepseek', model: 'deepseek-chat' },
        { providerId: 'deepseek', model: 'deepseek-reasoner' },
      ];
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await clickWhenShown('routing-enable');

      await waitFor(() => {
        expect(screen.getByTestId('smart-guard-step')).toBeInTheDocument();
      });
    });

    it.each([['guard-enable'], ['guard-skip']])('leads to the theme step after %s', async (buttonId) => {
      await renderPastWelcome();
      await passMigrationToolsAndHealth();

      await clickWhenShown(buttonId);

      await waitFor(() => {
        expect(screen.getByTestId('theme-onboarding-step')).toBeInTheDocument();
      });
    });
  });

  describe('theme step and completion', () => {
    it.each([['theme-continue'], ['theme-skip']])('completes onboarding after %s', async (buttonId) => {
      mockSecurityConfig.value = { autoReviewEnabled: true };
      const onComplete = vi.fn();
      await renderPastWelcome(onComplete);
      await passMigrationToolsAndHealth();

      await clickWhenShown(buttonId);

      await waitFor(() => {
        expect(mockCompleteOnboarding).toHaveBeenCalledTimes(1);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
  });
});
