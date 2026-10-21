import { describe, expect, it } from 'vitest';

import { isLoopbackProbeUrl, resolveProbeUrl } from './probe';

describe('isLoopbackProbeUrl', () => {
  it('accepts the loopback hosts the backend probe allowlist permits', () => {
    expect(isLoopbackProbeUrl('http://127.0.0.1:8000/mcp')).toBe(true);
    expect(isLoopbackProbeUrl('http://localhost:9876/sse')).toBe(true);
    expect(isLoopbackProbeUrl('http://[::1]:8000/mcp')).toBe(true);
    expect(isLoopbackProbeUrl('http://0.0.0.0:8000/mcp')).toBe(true);
  });

  it('rejects remote hosts so hosted MCP entries skip the probe', () => {
    expect(isLoopbackProbeUrl('https://mcp.postiz.com/mcp')).toBe(false);
    expect(isLoopbackProbeUrl('https://mcp.firecrawl.dev/v2/mcp')).toBe(false);
    expect(isLoopbackProbeUrl('https://docs.qq.com/openapi/mcp')).toBe(false);
  });

  it('rejects unparsable candidates instead of probing them', () => {
    expect(isLoopbackProbeUrl('not-a-url')).toBe(false);
    expect(isLoopbackProbeUrl('')).toBe(false);
  });
});

describe('resolveProbeUrl', () => {
  it('prefers an explicit loopback probeUrl over the entry url', () => {
    expect(resolveProbeUrl({ probeUrl: 'http://127.0.0.1:8000/mcp', url: 'https://example.com/mcp' })).toBe(
      'http://127.0.0.1:8000/mcp',
    );
  });

  it('falls back to a loopback entry url when probeUrl is missing', () => {
    expect(resolveProbeUrl({ url: 'http://127.0.0.1:7001/mcp' })).toBe('http://127.0.0.1:7001/mcp');
  });

  it('returns undefined for remote entries so the security gate verifies them instead', () => {
    expect(resolveProbeUrl({ url: 'https://mcp.postiz.com/mcp' })).toBeUndefined();
    expect(
      resolveProbeUrl({ probeUrl: 'https://mcp.example.com/mcp', url: 'https://mcp.example.com/mcp' }),
    ).toBeUndefined();
  });

  it('returns undefined without any usable url', () => {
    expect(resolveProbeUrl(null)).toBeUndefined();
    expect(resolveProbeUrl({})).toBeUndefined();
    expect(resolveProbeUrl({ url: '  ' })).toBeUndefined();
  });
});
