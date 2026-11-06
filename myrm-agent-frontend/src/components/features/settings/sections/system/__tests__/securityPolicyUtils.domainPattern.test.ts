import { describe, expect, it } from 'vitest';

import { DOMAIN_PATTERN } from '../securityPolicyUtils';

/** The spellings of a domain list entry the harness reads: `host`, `*.host`, `.host` and any of them with `:port`. */
describe('DOMAIN_PATTERN', () => {
  it.each([
    'example.com',
    'API.Example.com',
    'localhost',
    'xn--mnchen-3ya.de',
    '*.example.com',
    '.example.com',
    'example.com:8443',
    '*.example.com:8443',
    '.example.com:8443',
  ])('accepts %s', (entry) => {
    expect(DOMAIN_PATTERN.test(entry)).toBe(true);
  });

  it.each([
    '',
    '*',
    '*.',
    '.',
    '..example.com',
    '*.*.example.com',
    'a..b',
    '-a.com',
    'a-.com',
    'example.com:',
    'example.com:abc',
    'example.com:123456',
    'https://example.com',
    'example.com/path',
    'a b.com',
  ])('rejects %j', (entry) => {
    expect(DOMAIN_PATTERN.test(entry)).toBe(false);
  });
});
