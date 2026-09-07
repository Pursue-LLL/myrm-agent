/** @vitest-environment jsdom */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ProviderBalanceIndicator from '../ProviderBalanceIndicator';
import ProviderLowBalanceWarningHUD from '../ProviderLowBalanceWarningHUD';

const mockGetGauge = vi.fn();
const mockFetchGauges = vi.fn();
const mockUpdateAgentConfig = vi.fn();

vi.mock('@/store/useProviderBalanceStore', () => ({
  default: vi.fn((selector: (state: object) => unknown) =>
    selector({
      getGauge: mockGetGauge,
      fetchGauges: mockFetchGauges,
    }),
  ),
  useProviderBalanceStore: vi.fn((selector: (state: object) => unknown) =>
    selector({
      getGauge: mockGetGauge,
      fetchGauges: mockFetchGauges,
    }),
  ),
}));

vi.mock('@/store/useProviderStore', () => ({
  default: vi.fn((selector: (state: object) => unknown) =>
    selector({
      defaultModelConfig: {
        safetyFallbackModelSelection: {
          providerId: 'siliconflow',
          model: 'deepseek-ai/DeepSeek-V3',
        },
      },
    }),
  ),
}));

vi.mock('@/store/useChatStore', () => ({
  default: vi.fn((selector: (state: object) => unknown) =>
    selector({
      updateAgentConfig: mockUpdateAgentConfig,
    }),
  ),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ProviderBalanceIndicator & HUD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders healthy balance badge with dollar format', () => {
    mockGetGauge.mockReturnValue({
      provider_id: 'openrouter',
      balance: 15.5,
      currency: 'USD',
      status: 'healthy',
      details: 'Remaining allowance: $15.50',
    });

    render(<ProviderBalanceIndicator providerId="openrouter" />);
    const indicator = screen.getByTestId('provider-balance-indicator');
    expect(indicator).toBeInTheDocument();
    expect(indicator.textContent).toContain('$15.50');
  });

  it('renders nothing when provider is null or gauge not found', () => {
    mockGetGauge.mockReturnValue(undefined);
    const { container } = render(<ProviderBalanceIndicator providerId={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders critical HUD banner with switch button and executes fallback', () => {
    mockGetGauge.mockReturnValue({
      provider_id: 'deepseek',
      balance: 0.2,
      currency: 'CNY',
      status: 'critical',
      details: 'Official balance: 0.20 CNY',
    });

    render(<ProviderLowBalanceWarningHUD currentProviderId="deepseek" />);
    const hud = screen.getByTestId('provider-low-balance-warning-hud');
    expect(hud).toBeInTheDocument();
    expect(hud.textContent).toContain('hudCriticalTitle');

    const switchBtn = screen.getByRole('button', { name: /hudSwitchToFallback/i });
    expect(switchBtn).toBeInTheDocument();
    fireEvent.click(switchBtn);

    expect(mockUpdateAgentConfig).toHaveBeenCalledWith({
      provider: 'siliconflow',
      model: 'deepseek-ai/DeepSeek-V3',
    });
  });
});
