import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../../../locales/en.json';
import zh from '../../../../../../../locales/zh.json';
import { formatDueWindow } from '../followUpDueWindow';

// The global next-intl mock has no ICU engine; these checks need the real translator.
const { createTranslator } = await vi.importActual<typeof import('next-intl')>('next-intl');

const HOUR = 60 * 60 * 1000;
const NOW = Date.UTC(2026, 10, 3, 12, 0, 0);

type DueWindowTranslator = Parameters<typeof formatDueWindow>[2];

// The translator built from the JSON bundle is typed per key; the component receives the hook's translator type.
const translator = (locale: 'en' | 'zh') =>
  createTranslator({
    locale,
    messages: locale === 'en' ? en : zh,
    namespace: 'followUps',
  }) as unknown as DueWindowTranslator;

describe('formatDueWindow', () => {
  it('reads upcoming windows in hours, then in days from 24 hours on', () => {
    const t = translator('en');

    expect(formatDueWindow(NOW + 10 * 60 * 1000, NOW, t)).toBe('Under 1 hour');
    expect(formatDueWindow(NOW + 30 * 60 * 1000, NOW, t)).toBe('In 1 hour');
    expect(formatDueWindow(NOW + HOUR, NOW, t)).toBe('In 1 hour');
    expect(formatDueWindow(NOW + 5 * HOUR, NOW, t)).toBe('In 5 hours');
    expect(formatDueWindow(NOW + 48 * HOUR, NOW, t)).toBe('In 2 days');
  });

  it('reads overdue windows the same way', () => {
    const t = translator('en');

    expect(formatDueWindow(NOW - 10 * 60 * 1000, NOW, t)).toBe('Overdue under 1 hour');
    expect(formatDueWindow(NOW - 3 * HOUR, NOW, t)).toBe('Overdue 3 hours');
    expect(formatDueWindow(NOW - 72 * HOUR, NOW, t)).toBe('Overdue 3 days');
  });

  it('speaks Chinese when the interface is Chinese', () => {
    const t = translator('zh');

    expect(formatDueWindow(NOW + 5 * HOUR, NOW, t)).toBe('5小时后');
    expect(formatDueWindow(NOW - 48 * HOUR, NOW, t)).toBe('逾期2天');
    expect(formatDueWindow(NOW + 10 * 60 * 1000, NOW, t)).toBe('不到1小时');
    expect(formatDueWindow(NOW - 10 * 60 * 1000, NOW, t)).toBe('逾期不到1小时');
  });
});
