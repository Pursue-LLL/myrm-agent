import { describe, expect, it } from 'vitest';
import { mergeBillingCatalog } from '@/lib/billing-plans';
import type { BillingCatalogPlan } from '@/lib/cp-billing';

function planEntry(overrides: Partial<BillingCatalogPlan> & { plan: BillingCatalogPlan['plan'] }): BillingCatalogPlan {
  return {
    monthly_usd: 49,
    yearly_usd: 490,
    monthly_wu: 10000,
    trial_days: 0,
    checkout_available: true,
    yearly_checkout_available: true,
    features: [],
    ...overrides,
  };
}

describe('mergeBillingCatalog yearly guard', () => {
  it('carries yearly checkout availability per plan', () => {
    const entries = mergeBillingCatalog([
      planEntry({ plan: 'pro', checkout_available: true, yearly_checkout_available: false }),
    ]);
    const pro = entries.find((entry) => entry.key === 'pro');
    expect(pro?.checkoutAvailable).toBe(true);
    expect(pro?.yearlyCheckoutAvailable).toBe(false);
  });

  it('defaults yearly availability to false when the catalog omits it', () => {
    const remote = planEntry({ plan: 'plus' });
    delete (remote as Partial<BillingCatalogPlan>).yearly_checkout_available;
    const entries = mergeBillingCatalog([remote]);
    expect(entries.find((entry) => entry.key === 'plus')?.yearlyCheckoutAvailable).toBe(false);
  });
});
