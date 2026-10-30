import { describe, expect, it } from 'vitest';

import { isProxyUrlInvalid } from '../proxy-url';

describe('isProxyUrlInvalid', () => {
  it.each([undefined, '', '   '])('treats a blank value (%j) as not invalid, since a proxy is optional', (value) => {
    expect(isProxyUrlInvalid(value)).toBe(false);
  });

  it.each([
    'http://127.0.0.1:7890',
    'https://proxy.example.com:8443',
    'socks5://127.0.0.1:1080',
    'socks5h://user:pass@proxy.lan:1080',
    '  SOCKS5://127.0.0.1:1080  ',
  ])('accepts %j', (value) => {
    expect(isProxyUrlInvalid(value)).toBe(false);
  });

  it.each(['127.0.0.1:7890', 'ftp://127.0.0.1:21', 'socks4://127.0.0.1:1080', 'http://', 'http:// bad host', 'proxy'])(
    'flags %j',
    (value) => {
      expect(isProxyUrlInvalid(value)).toBe(true);
    },
  );
});
