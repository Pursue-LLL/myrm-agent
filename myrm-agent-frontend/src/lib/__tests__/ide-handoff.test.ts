import { describe, expect, it } from 'vitest';
import { buildIdeDeepLink, IDE_HANDOFF_TARGETS, isIdeHandoffTarget } from '@/lib/ide-handoff';

describe('ide-handoff deep links', () => {
  it('builds OS-handled links per target', () => {
    expect(buildIdeDeepLink('cursor')).toBe('cursor://');
    expect(buildIdeDeepLink('vscode')).toBe('vscode://');
  });

  it('exposes exactly the supported targets', () => {
    expect([...IDE_HANDOFF_TARGETS]).toEqual(['cursor', 'vscode']);
  });

  it('guards target values', () => {
    expect(isIdeHandoffTarget('cursor')).toBe(true);
    expect(isIdeHandoffTarget('sublime')).toBe(false);
  });
});
