import { describe, expect, it } from 'vitest';
import { normalizeDomainInput, parseOverrides, serializeOverrides } from '../agentSecurityOverrides';

describe('normalizeDomainInput', () => {
  it('lowercases, trims and strips the scheme and path', () => {
    expect(normalizeDomainInput('  HTTPS://Example.COM/a/b?q=1 ')).toBe('example.com');
    expect(normalizeDomainInput('http://Sub.Example.com')).toBe('sub.example.com');
  });

  it('keeps ports and bare hosts untouched', () => {
    expect(normalizeDomainInput('example.com:8080/x')).toBe('example.com:8080');
    expect(normalizeDomainInput('example.com')).toBe('example.com');
  });

  it('returns an empty string for blank input', () => {
    expect(normalizeDomainInput('   ')).toBe('');
  });
});

describe('parseOverrides', () => {
  it('returns empty defaults for null', () => {
    expect(parseOverrides(null)).toEqual({
      capabilities: [],
      allowedRoots: [],
      approvalTimeoutSeconds: null,
      networkAllowlist: [],
      networkBlocklist: [],
      commandDenylist: [],
      domainHitlEnabled: false,
      injectionPolicy: null,
    });
  });

  it('reads every field, including the nested path policy', () => {
    expect(
      parseOverrides({
        capabilities: ['shell_exec'],
        pathPolicy: { allowedRoots: ['/data'] },
        approvalTimeoutSeconds: 90,
        networkAllowlist: ['a.com'],
        networkBlocklist: ['b.com'],
        commandDenylist: ['rm -rf*'],
        domainHitlEnabled: true,
        injectionPolicy: 'fail_closed',
      }),
    ).toEqual({
      capabilities: ['shell_exec'],
      allowedRoots: ['/data'],
      approvalTimeoutSeconds: 90,
      networkAllowlist: ['a.com'],
      networkBlocklist: ['b.com'],
      commandDenylist: ['rm -rf*'],
      domainHitlEnabled: true,
      injectionPolicy: 'fail_closed',
    });
  });

  it('falls back to defaults for malformed values', () => {
    const parsed = parseOverrides({
      capabilities: 'shell_exec',
      pathPolicy: { allowedRoots: 'nope' },
      approvalTimeoutSeconds: '30',
      networkAllowlist: {},
      domainHitlEnabled: 'true',
      injectionPolicy: 'strict',
    });
    expect(parsed.capabilities).toEqual([]);
    expect(parsed.allowedRoots).toEqual([]);
    expect(parsed.approvalTimeoutSeconds).toBeNull();
    expect(parsed.networkAllowlist).toEqual([]);
    expect(parsed.domainHitlEnabled).toBe(false);
    expect(parsed.injectionPolicy).toBeNull();
  });

  it('accepts the log_only injection policy', () => {
    expect(parseOverrides({ injectionPolicy: 'log_only' }).injectionPolicy).toBe('log_only');
  });
});

describe('serializeOverrides', () => {
  it('returns null when nothing is configured', () => {
    expect(serializeOverrides(parseOverrides(null))).toBeNull();
    expect(serializeOverrides(parseOverrides({}))).toBeNull();
  });

  it('emits only the configured keys', () => {
    const data = { ...parseOverrides(null), allowedRoots: ['/data'], domainHitlEnabled: true };
    expect(serializeOverrides(data)).toEqual({ pathPolicy: { allowedRoots: ['/data'] }, domainHitlEnabled: true });
  });

  it('keeps a zero timeout and a log_only policy as content', () => {
    expect(serializeOverrides({ ...parseOverrides(null), approvalTimeoutSeconds: 0 })).toEqual({
      approvalTimeoutSeconds: 0,
    });
    expect(serializeOverrides({ ...parseOverrides(null), injectionPolicy: 'log_only' })).toEqual({
      injectionPolicy: 'log_only',
    });
  });

  it('round-trips a fully populated record', () => {
    const raw = {
      capabilities: ['net_fetch', 'file_read'],
      pathPolicy: { allowedRoots: ['/a', '/b'] },
      approvalTimeoutSeconds: 120,
      networkAllowlist: ['a.com'],
      networkBlocklist: ['evil.com'],
      commandDenylist: ['git push --force*'],
      domainHitlEnabled: true,
      injectionPolicy: 'fail_closed',
    };
    expect(serializeOverrides(parseOverrides(raw))).toEqual(raw);
  });
});
