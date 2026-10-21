import { describe, expect, it } from 'vitest';

import {
  defaultAllowAlwaysScope,
  durationToTtlSeconds,
  scopeToAllowAlwaysValue,
} from '@/lib/approval/allowAlwaysScope';

describe('durationToTtlSeconds', () => {
  it('returns -1 for session scope duration', () => {
    expect(durationToTtlSeconds('session')).toBe(-1);
  });

  it('returns 900 for 15m duration', () => {
    expect(durationToTtlSeconds('15m')).toBe(900);
  });

  it('returns 3600 for 1h duration', () => {
    expect(durationToTtlSeconds('1h')).toBe(3600);
  });

  it('returns undefined for permanent duration', () => {
    expect(durationToTtlSeconds('permanent')).toBeUndefined();
  });
});

describe('scopeToAllowAlwaysValue', () => {
  it('maps permission scope with permanent duration to true', () => {
    expect(scopeToAllowAlwaysValue('permission', 'permanent')).toBe(true);
  });

  it('maps permission scope with session duration to object with ttl metadata', () => {
    expect(scopeToAllowAlwaysValue('permission', 'session')).toEqual({
      tool: false,
      duration: 'session',
      ttl_seconds: -1,
    });
  });

  it('maps tool scope with 15m duration to tool allowlist with 900s ttl', () => {
    expect(scopeToAllowAlwaysValue('tool', '15m')).toEqual({
      tool: true,
      duration: '15m',
      ttl_seconds: 900,
    });
  });

  it('maps exact scope with 1h duration to tool and args allowlist with 3600s ttl', () => {
    expect(scopeToAllowAlwaysValue('exact', '1h')).toEqual({
      tool: true,
      args: true,
      duration: '1h',
      ttl_seconds: 3600,
    });
  });

  it('maps pattern scope with permanent duration', () => {
    expect(scopeToAllowAlwaysValue('pattern', 'permanent')).toEqual({
      tool: true,
      pattern: true,
      duration: 'permanent',
    });
  });
});

describe('defaultAllowAlwaysScope', () => {
  it('defaults shell tools to exact', () => {
    expect(defaultAllowAlwaysScope('bash_code_execute_tool')).toBe('exact');
    expect(defaultAllowAlwaysScope('execute_code')).toBe('exact');
  });

  it('defaults non-shell tools to tool scope', () => {
    expect(defaultAllowAlwaysScope('file_write_tool')).toBe('tool');
  });
});
