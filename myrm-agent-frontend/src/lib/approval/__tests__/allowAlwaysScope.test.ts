import { describe, expect, it } from 'vitest';

import {
  defaultAllowAlwaysScope,
  scopeToAllowAlwaysValue,
} from '@/lib/approval/allowAlwaysScope';

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

  it('maps pattern scope to tool and pattern allowlist', () => {
    expect(scopeToAllowAlwaysValue('pattern')).toEqual({ tool: true, pattern: true });
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
