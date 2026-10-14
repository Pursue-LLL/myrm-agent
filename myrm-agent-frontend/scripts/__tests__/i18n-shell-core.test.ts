// @vitest-environment node
import { describe, expect, it } from 'vitest';

import { hasNonAsciiLetter, isLegitSameValue, isTranslationShell } from '../i18n-shell-core.mjs';

const NO_ALLOWLIST = { allowedSameValues: new Set<string>(), allowedSameKeys: new Set<string>() };

describe('hasNonAsciiLetter', () => {
  it('counts letters and combining marks outside ASCII', () => {
    expect(hasNonAsciiLetter('Café')).toBe(true);
    expect(hasNonAsciiLetter('設定')).toBe(true);
    expect(hasNonAsciiLetter('한국어')).toBe(true);
  });

  it('ignores ASCII and non-ASCII punctuation or symbols', () => {
    expect(hasNonAsciiLetter('Please wait...')).toBe(false);
    expect(hasNonAsciiLetter('Please wait… — done · ©')).toBe(false);
    expect(hasNonAsciiLetter('{count} × {max} → {total}')).toBe(false);
  });
});

describe('isLegitSameValue', () => {
  it('treats values with a non-ASCII letter as already localized', () => {
    expect(isLegitSameValue('Café Müller')).toBe(true);
    expect(isLegitSameValue('MyrmAgent 設定')).toBe(true);
  });

  it('does not let non-ASCII punctuation or symbols stand in for a translation', () => {
    expect(isLegitSameValue('Loading…')).toBe(false);
    expect(isLegitSameValue('Budget exceeded — execution blocked')).toBe(false);
    expect(isLegitSameValue('Version {version} · Device {device}')).toBe(false);
    expect(isLegitSameValue('© {year} MyrmAgent. All rights reserved.')).toBe(false);
    expect(isLegitSameValue('Space: play/pause · ←/→: step frame')).toBe(false);
  });

  it('keeps concrete formats legitimate', () => {
    expect(isLegitSameValue('https://example.com/docs')).toBe(true);
    expect(isLegitSameValue('/guides/tunnel')).toBe(true);
    expect(isLegitSameValue('ops@example.com')).toBe(true);
    expect(isLegitSameValue('MCP')).toBe(true);
    expect(isLegitSameValue('{count} / {max}')).toBe(true);
    expect(isLegitSameValue('{count} × {max} → {total}')).toBe(true);
  });

  it('still flags plain English words and sentences', () => {
    expect(isLegitSameValue('Active')).toBe(false);
    expect(isLegitSameValue('Task {taskId} resumed')).toBe(false);
  });
});

describe('isTranslationShell', () => {
  it('flags a locale value that merely repeats an English value carrying a symbol', () => {
    const en = 'Restoring…';
    expect(isTranslationShell('agent.timeMachine.restoring', en, en, NO_ALLOWLIST)).toBe(true);
    expect(isTranslationShell('agent.timeMachine.restoring', en, 'Wird wiederhergestellt…', NO_ALLOWLIST)).toBe(false);
  });

  it('honours the explicit allowlist by value and by key', () => {
    const en = 'MoA · {preset}';
    const byValue = { allowedSameValues: new Set([en]), allowedSameKeys: new Set<string>() };
    const byKey = { allowedSameValues: new Set<string>(), allowedSameKeys: new Set(['k.moa']) };
    expect(isTranslationShell('k.moa', en, en, NO_ALLOWLIST)).toBe(true);
    expect(isTranslationShell('k.moa', en, en, byValue)).toBe(false);
    expect(isTranslationShell('k.moa', en, en, byKey)).toBe(false);
  });
});
