import { describe, expect, it } from 'vitest';

import { isHiddenBuiltinAgent, resolveVisibleBuiltinAgentId } from '../product-surface';

describe('product surface', () => {
  it('reports the hidden presets as hidden and the general agent as visible', () => {
    expect(isHiddenBuiltinAgent('builtin-researcher')).toBe(true);
    expect(isHiddenBuiltinAgent('builtin-ko-office')).toBe(true);
    expect(isHiddenBuiltinAgent('builtin-general')).toBe(false);
    expect(isHiddenBuiltinAgent(null)).toBe(false);
  });

  it('sends a chat that names a hidden preset to the general agent', () => {
    expect(resolveVisibleBuiltinAgentId('builtin-ko-office')).toBe('builtin-general');
    expect(resolveVisibleBuiltinAgentId('builtin-ko-office', 'builtin-economy')).toBe('builtin-economy');
  });

  it('keeps every other agent id and falls back when none is given', () => {
    expect(resolveVisibleBuiltinAgentId('builtin-coder')).toBe('builtin-coder');
    expect(resolveVisibleBuiltinAgentId('custom-agent-1')).toBe('custom-agent-1');
    expect(resolveVisibleBuiltinAgentId(undefined)).toBe('builtin-general');
  });
});
