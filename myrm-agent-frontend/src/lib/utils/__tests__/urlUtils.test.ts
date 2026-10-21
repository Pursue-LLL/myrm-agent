import { describe, expect, it } from 'vitest';
import {
  isValidExternalUrl,
  isValidPublicIngressBaseUrl,
  normalizePublicIngressBaseUrl,
} from '../urlUtils';

describe('isValidExternalUrl', () => {
  it('should accept standard http and https URLs', () => {
    expect(isValidExternalUrl('https://example.com')).toBe(true);
    expect(isValidExternalUrl('http://localhost:3000')).toBe(true);
    expect(isValidExternalUrl('https://myrm.dev/docs/wiki?page=1#heading')).toBe(true);
  });

  it('should reject dangerous javascript: and data: URLs', () => {
    expect(isValidExternalUrl('javascript:alert(1)')).toBe(false);
    expect(isValidExternalUrl('javascript://example.com?http://evil.com')).toBe(false);
    expect(isValidExternalUrl('data:text/html;base64,PHNjcmlwdD4=')).toBe(false);
  });

  it('should reject file: and custom desktop schemes to prevent escape', () => {
    expect(isValidExternalUrl('file:///etc/passwd')).toBe(false);
    expect(isValidExternalUrl('custom-protocol://action')).toBe(false);
    expect(isValidExternalUrl('tauri://ipc')).toBe(false);
  });

  it('should reject empty or malformed inputs', () => {
    expect(isValidExternalUrl('')).toBe(false);
    expect(isValidExternalUrl('   ')).toBe(false);
    expect(isValidExternalUrl('not a url')).toBe(false);
  });
});

describe('publicIngressUrl', () => {
  it('normalize trims and strips trailing slashes', () => {
    expect(normalizePublicIngressBaseUrl('  https://a.example.com/  ')).toBe(
      'https://a.example.com'
    );
    expect(normalizePublicIngressBaseUrl('')).toBe('');
  });

  it('validate accepts empty or https only', () => {
    expect(isValidPublicIngressBaseUrl('')).toBe(true);
    expect(isValidPublicIngressBaseUrl('https://a.example.com')).toBe(true);
    expect(isValidPublicIngressBaseUrl('http://a.example.com')).toBe(false);
    expect(isValidPublicIngressBaseUrl('not-a-url')).toBe(false);
  });
});
