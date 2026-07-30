import { describe, expect, it } from 'vitest';

import {
  claimStatusClass,
  claimStatusLabel,
  shouldShowClaimConfidence,
  shouldShowClaimStatusBadge,
  type WikiClaimStatusLabels,
} from '../claimStatusDisplay';

const labels: WikiClaimStatusLabels = {
  supported: 'Supported',
  contested: 'Contested',
  unsupported: 'Unsupported',
  unknown: 'Unknown',
};

describe('claimStatusDisplay', () => {
  it('shouldShowClaimStatusBadge only surfaces contested and unsupported', () => {
    expect(shouldShowClaimStatusBadge('contested')).toBe(true);
    expect(shouldShowClaimStatusBadge('unsupported')).toBe(true);
    expect(shouldShowClaimStatusBadge('supported')).toBe(false);
    expect(shouldShowClaimStatusBadge('unknown')).toBe(false);
    expect(shouldShowClaimStatusBadge(undefined)).toBe(false);
  });

  it('claimStatusLabel maps known statuses', () => {
    expect(claimStatusLabel('contested', labels)).toBe('Contested');
    expect(claimStatusLabel('unsupported', labels)).toBe('Unsupported');
    expect(claimStatusLabel('other', labels)).toBe('Unknown');
  });

  it('claimStatusClass returns semantic classes', () => {
    expect(claimStatusClass('contested')).toContain('amber');
    expect(claimStatusClass('unsupported')).toContain('red');
  });

  it('shouldShowClaimConfidence hides fallback 0.5', () => {
    expect(shouldShowClaimConfidence(undefined)).toBe(false);
    expect(shouldShowClaimConfidence(0.5)).toBe(false);
    expect(shouldShowClaimConfidence(0.91)).toBe(true);
  });
});
