import { describe, expect, it } from 'vitest';
import { isValidPublicIngressBaseUrl, normalizePublicIngressBaseUrl } from '@/lib/utils/urlUtils';

describe('publicIngressUrl', () => {
  it('normalize trims and strips trailing slashes', () => {
    expect(normalizePublicIngressBaseUrl('  https://a.example.com/  ')).toBe('https://a.example.com');
    expect(normalizePublicIngressBaseUrl('')).toBe('');
  });

  it('validate accepts empty or https only', () => {
    expect(isValidPublicIngressBaseUrl('')).toBe(true);
    expect(isValidPublicIngressBaseUrl('https://a.example.com')).toBe(true);
    expect(isValidPublicIngressBaseUrl('http://a.example.com')).toBe(false);
    expect(isValidPublicIngressBaseUrl('not-a-url')).toBe(false);
  });
});
