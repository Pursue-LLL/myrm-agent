import { describe, expect, it } from 'vitest';

import { stripEntitlementBlockedBuiltinTools } from '@/lib/builtin-tool-entitlements';

describe('stripEntitlementBlockedBuiltinTools', () => {
  it('returns tools unchanged outside sandbox', () => {
    expect(
      stripEntitlementBlockedBuiltinTools(['web_search', 'computer_use', 'cron'], {
        sandbox: false,
        canUseCron: false,
        canUseVnc: false,
      }),
    ).toEqual(['web_search', 'computer_use', 'cron']);
  });

  it('removes cron and computer_use when sandbox lacks entitlements', () => {
    expect(
      stripEntitlementBlockedBuiltinTools(['web_search', 'computer_use', 'cron'], {
        sandbox: true,
        canUseCron: false,
        canUseVnc: false,
      }),
    ).toEqual(['web_search']);
  });

  it('removes external_cli in sandbox regardless of entitlements', () => {
    expect(
      stripEntitlementBlockedBuiltinTools(['web_search', 'external_cli', 'memory'], {
        sandbox: true,
        canUseCron: true,
        canUseVnc: true,
      }),
    ).toEqual(['web_search', 'memory']);
  });

  it('keeps entitled sandbox tools', () => {
    expect(
      stripEntitlementBlockedBuiltinTools(['browser', 'computer_use', 'cron'], {
        sandbox: true,
        canUseCron: true,
        canUseVnc: true,
      }),
    ).toEqual(['browser', 'computer_use', 'cron']);
  });
});
