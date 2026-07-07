import { describe, expect, it } from 'vitest';
import { fingerprintValue, valuesEqual } from '@/services/config/configFingerprint';

describe('configFingerprint', () => {
  it('treats key order as equal', () => {
    expect(valuesEqual({ a: 1, b: 2 }, { b: 2, a: 1 })).toBe(true);
  });

  it('detects real changes', () => {
    expect(valuesEqual({ a: 1 }, { a: 2 })).toBe(false);
  });

  it('produces stable fingerprints', () => {
    expect(fingerprintValue({ z: 1, a: 2 })).toBe(fingerprintValue({ a: 2, z: 1 }));
  });
});
