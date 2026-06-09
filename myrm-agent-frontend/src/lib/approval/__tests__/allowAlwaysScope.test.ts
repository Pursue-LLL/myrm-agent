import { describe, expect, it } from 'vitest';

import { scopeToAllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';

describe('scopeToAllowAlwaysValue', () => {
  it('maps permission scope to true', () => {
    expect(scopeToAllowAlwaysValue('permission')).toBe(true);
  });

  it('maps tool scope to tool-only allowlist', () => {
    expect(scopeToAllowAlwaysValue('tool')).toEqual({ tool: true });
  });

  it('maps exact scope to tool and args allowlist', () => {
    expect(scopeToAllowAlwaysValue('exact')).toEqual({ tool: true, args: true });
  });
});
