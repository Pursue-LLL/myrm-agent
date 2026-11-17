import { describe, expect, it } from 'vitest';
import { isLocalOrTrustedSplitStackApiUrl, isTrustedSplitStackHostname } from '../trustedSplitStackEndpoint';

describe('isTrustedSplitStackHostname and URL helpers', () => {
  it('correctly classifies loopback, RFC1918, Tailscale, and mDNS as trusted split-stack hostnames', () => {
    expect(isTrustedSplitStackHostname('localhost')).toBe(true);
    expect(isTrustedSplitStackHostname('127.0.0.1')).toBe(true);
    expect(isTrustedSplitStackHostname('10.0.0.1')).toBe(true);
    expect(isTrustedSplitStackHostname('172.16.0.1')).toBe(true);
    expect(isTrustedSplitStackHostname('172.31.255.254')).toBe(true);
    expect(isTrustedSplitStackHostname('192.168.1.100')).toBe(true);
    expect(isTrustedSplitStackHostname('100.80.20.10')).toBe(true);
    expect(isTrustedSplitStackHostname('mac-mini.local')).toBe(true);
  });

  it('rejects cloud link-local metadata, public IPs, and external domains', () => {
    expect(isTrustedSplitStackHostname('169.254.169.254')).toBe(false);
    expect(isTrustedSplitStackHostname('8.8.8.8')).toBe(false);
    expect(isTrustedSplitStackHostname('api.openai.com')).toBe(false);
    expect(isTrustedSplitStackHostname('172.15.0.1')).toBe(false);
    expect(isTrustedSplitStackHostname('172.32.0.1')).toBe(false);
  });

  it('correctly evaluates full API URLs for local or split-stack hosting', () => {
    expect(isLocalOrTrustedSplitStackApiUrl('http://127.0.0.1:11434/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://192.168.1.50:11434/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('192.168.1.50:11434/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('100.80.20.10:8000')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://100.80.20.10:8000/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://dgx-spark.local:8000/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('https://api.openai.com/v1')).toBe(false);
    expect(isLocalOrTrustedSplitStackApiUrl('')).toBe(false);
    expect(isLocalOrTrustedSplitStackApiUrl(null)).toBe(false);
  });

  it('rigorously tests exact CIDR boundaries for RFC1918 and Tailscale CGNAT', () => {
    // 172.16.0.0/12 boundaries
    expect(isTrustedSplitStackHostname('172.15.255.255')).toBe(false);
    expect(isTrustedSplitStackHostname('172.16.0.0')).toBe(true);
    expect(isTrustedSplitStackHostname('172.31.255.255')).toBe(true);
    expect(isTrustedSplitStackHostname('172.32.0.0')).toBe(false);

    // Tailscale 100.64.0.0/10 boundaries
    expect(isTrustedSplitStackHostname('100.63.255.255')).toBe(false);
    expect(isTrustedSplitStackHostname('100.64.0.0')).toBe(true);
    expect(isTrustedSplitStackHostname('100.127.255.255')).toBe(true);
    expect(isTrustedSplitStackHostname('100.128.0.0')).toBe(false);

    // Link-local boundaries
    expect(isTrustedSplitStackHostname('169.254.0.1')).toBe(false);
    expect(isTrustedSplitStackHostname('169.254.255.254')).toBe(false);
  });

  it('ignores case, surrounding spaces and IPv6 brackets, and trusts the IPv6 and unspecified loopbacks', () => {
    expect(isTrustedSplitStackHostname(' Mac-Mini.LOCAL ')).toBe(true);
    expect(isTrustedSplitStackHostname('::1')).toBe(true);
    expect(isTrustedSplitStackHostname('[::1]')).toBe(true);
    expect(isTrustedSplitStackHostname('0.0.0.0')).toBe(true);
  });

  it('trusts the whole 127.0.0.0/8 loopback block', () => {
    expect(isTrustedSplitStackHostname('127.1.2.3')).toBe(true);
  });

  it('rejects dotted names that are not four valid octets', () => {
    expect(isTrustedSplitStackHostname('10.0.0.256')).toBe(false);
    expect(isTrustedSplitStackHostname('10.0.0.-1')).toBe(false);
    expect(isTrustedSplitStackHostname('10.0.0.x')).toBe(false);
    expect(isTrustedSplitStackHostname('10.0.0')).toBe(false);
    expect(isTrustedSplitStackHostname('10.0.0.1.5')).toBe(false);
  });

  it('judges the host of a bracketed IPv6 URL, tolerates surrounding spaces and rejects an unparseable URL', () => {
    expect(isLocalOrTrustedSplitStackApiUrl('http://[::1]:8080/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('  http://localhost:11434  ')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://')).toBe(false);
  });
});
