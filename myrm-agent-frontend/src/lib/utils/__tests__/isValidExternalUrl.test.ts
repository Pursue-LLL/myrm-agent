import { describe, it, expect } from 'vitest';
import { isValidExternalUrl } from '../urlUtils';

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
