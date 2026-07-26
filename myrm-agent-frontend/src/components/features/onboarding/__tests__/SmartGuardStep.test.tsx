import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockSyncManagerGet = vi.fn();
const mockSyncManagerSet = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: mockSyncManagerGet,
    set: mockSyncManagerSet,
  }),
}));

vi.mock('@/services/config/types', () => ({}));

const mockProviders = vi.hoisted(() => ({ value: [] as unknown[] }));
const mockEnabledModels = vi.hoisted(() => ({
  value: [] as { providerId: string; model: string }[],
}));

vi.mock('@/store/useProviderStore', () => ({
  default: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      providers: mockProviders.value,
      getEnabledModels: () => mockEnabledModels.value,
    }),
}));

vi.mock('@/components/features/settings/default-model/EnabledModelSelect', () => ({
  default: ({
    value,
    onChange,
    label,
  }: {
    value: { providerId: string; model: string } | null;
    onChange: (v: { providerId: string; model: string } | null) => void;
    label: string;
  }) => (
    <div data-testid="model-select" data-label={label}>
      <span data-testid="selected-model">{value ? `${value.providerId}/${value.model}` : 'none'}</span>
      <button data-testid="change-model" onClick={() => onChange({ providerId: 'p2', model: 'gpt-4o-mini' })}>
        change
      </button>
      <button data-testid="clear-model" onClick={() => onChange(null)}>
        clear
      </button>
    </div>
  ),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconShieldCheck: ({ className }: { className: string }) => (
    <svg data-testid="shield-icon" className={className} />
  ),
}));

vi.mock('@/components/features/settings/sections/system/securityPolicyUtils', () => ({
  DEFAULT_CONFIG: {
    permissions: { read: true, write: false },
    approvalTimeoutSeconds: 120,
    autoReviewEnabled: false,
    autoReviewModel: null,
  },
}));

import SmartGuardStep from '../SmartGuardStep';

describe('SmartGuardStep', () => {
  const onComplete = vi.fn();
  const onSkip = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockProviders.value = [{ id: 'openai', name: 'OpenAI' }];
    mockEnabledModels.value = [
      { providerId: 'openai', model: 'gpt-4o' },
      { providerId: 'openai', model: 'gpt-4o-mini' },
    ];
    mockSyncManagerGet.mockReturnValue(null);
  });

  it('renders with switch enabled by default', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    const switchEl = screen.getByRole('switch');
    expect(switchEl).toBeInTheDocument();
    expect(switchEl).toHaveAttribute('data-state', 'checked');
  });

  it('pre-selects cheapest model (contains "mini")', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    const selected = screen.getByTestId('selected-model');
    expect(selected.textContent).toBe('openai/gpt-4o-mini');
  });

  it('falls back to first model when no cheap keyword found', () => {
    mockEnabledModels.value = [
      { providerId: 'anthropic', model: 'claude-3-opus' },
      { providerId: 'anthropic', model: 'claude-3-sonnet' },
    ];

    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    const selected = screen.getByTestId('selected-model');
    expect(selected.textContent).toBe('anthropic/claude-3-opus');
  });

  it('hides model select when switch is toggled off', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    expect(screen.getByTestId('model-select')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch'));

    expect(screen.queryByTestId('model-select')).not.toBeInTheDocument();
  });

  it('calls onSkip when skip button is clicked', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    const skipBtn = screen.getByRole('button', { name: 'skip' });
    fireEvent.click(skipBtn);

    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('calls onSkip when confirm clicked while switch is off', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole('switch'));

    const buttons = screen.getAllByRole('button', { name: 'skip' });
    fireEvent.click(buttons[buttons.length - 1]);

    expect(onSkip).toHaveBeenCalled();
  });

  it('saves config and calls onComplete when enable clicked', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    const enableBtn = screen.getByRole('button', { name: 'enable' });
    fireEvent.click(enableBtn);

    expect(mockSyncManagerSet).toHaveBeenCalledWith('securityConfig', expect.objectContaining({
      autoReviewEnabled: true,
      autoReviewModel: 'openai/gpt-4o-mini',
    }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('uses DEFAULT_CONFIG when current security config is null', () => {
    mockSyncManagerGet.mockReturnValue(null);

    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole('button', { name: 'enable' }));

    expect(mockSyncManagerSet).toHaveBeenCalledWith('securityConfig', expect.objectContaining({
      permissions: { read: true, write: false },
      approvalTimeoutSeconds: 120,
      autoReviewEnabled: true,
    }));
  });

  it('preserves existing config fields when saving', () => {
    mockSyncManagerGet.mockReturnValue({
      permissions: { read: true, write: true },
      approvalTimeoutSeconds: 60,
      autoReviewEnabled: false,
      autoReviewModel: null,
      customField: 'keep-me',
    });

    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByRole('button', { name: 'enable' }));

    expect(mockSyncManagerSet).toHaveBeenCalledWith('securityConfig', expect.objectContaining({
      permissions: { read: true, write: true },
      approvalTimeoutSeconds: 60,
      customField: 'keep-me',
      autoReviewEnabled: true,
      autoReviewModel: 'openai/gpt-4o-mini',
    }));
  });

  it('disables enable button when model is cleared', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByTestId('clear-model'));

    const enableBtn = screen.getByRole('button', { name: 'enable' });
    expect(enableBtn).toBeDisabled();
  });

  it('does not call onComplete when enable clicked with no model', () => {
    mockEnabledModels.value = [];

    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    const enableBtn = screen.getByRole('button', { name: 'enable' });
    fireEvent.click(enableBtn);

    expect(mockSyncManagerSet).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('handles model change and saves new selection', () => {
    render(<SmartGuardStep onComplete={onComplete} onSkip={onSkip} />);

    fireEvent.click(screen.getByTestId('change-model'));

    fireEvent.click(screen.getByRole('button', { name: 'enable' }));

    expect(mockSyncManagerSet).toHaveBeenCalledWith('securityConfig', expect.objectContaining({
      autoReviewModel: 'p2/gpt-4o-mini',
    }));
  });
});
