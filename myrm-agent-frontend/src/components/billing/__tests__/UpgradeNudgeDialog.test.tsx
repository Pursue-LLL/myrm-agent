/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

vi.mock('@/lib/deploy-mode', () => ({ isSandbox: () => true }));

vi.mock('@/store/useUpgradeNudgeStore', () => ({
  useUpgradeNudgeStore: () => ({ open: true, trigger: 'feature_gate', blockedFeature: 'cron', close: vi.fn() }),
}));

vi.mock('@/hooks/billing/useSubscription', () => ({
  useSubscription: () => ({ subscription: { plan_type: 'free' } }),
}));

vi.mock('@/hooks/billing/useEntitlements', () => ({
  useEntitlements: () => ({ entitlements: { balance_wu: 10, monthly_allowance_wu: 100 } }),
}));

vi.mock('@/hooks/billing/useBillingCatalog', () => ({
  useBillingCatalog: () => ({
    catalog: {
      plans: [
        {
          plan: 'companion',
          monthly_usd: 9,
          yearly_usd: 90,
          monthly_wu: 1000,
          trial_days: 0,
          checkout_available: true,
          yearly_checkout_available: true,
          features: ['cron', 'brand_new_feature'],
        },
      ],
    },
  }),
}));

import UpgradeNudgeDialog from '../UpgradeNudgeDialog';

describe('UpgradeNudgeDialog recommended plan features', () => {
  afterEach(cleanup);

  it('translates a feature the language pack knows', () => {
    render(<UpgradeNudgeDialog />);

    expect(screen.getByText('Scheduled automation')).toBeInTheDocument();
  });

  it('shows a feature the language pack does not know as the plan catalog sent it', () => {
    render(<UpgradeNudgeDialog />);

    expect(screen.getByText('brand_new_feature')).toBeInTheDocument();
    expect(screen.queryByText(/nudge\.features/)).toBeNull();
  });
});
