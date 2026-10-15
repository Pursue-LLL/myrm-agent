import { describe, expect, it } from 'vitest';

import de from '../../../../../locales/de.json';
import en from '../../../../../locales/en.json';
import ja from '../../../../../locales/ja.json';
import ko from '../../../../../locales/ko.json';
import zh from '../../../../../locales/zh.json';
import zhTW from '../../../../../locales/zh-TW.json';
import { DOCTOR_LOCALE_KEYS } from '../doctorReportView';

type Messages = typeof en;

const LOCALES: readonly (readonly [string, Messages])[] = [
  ['de', de],
  ['en', en],
  ['ja', ja],
  ['ko', ko],
  ['zh', zh],
  ['zh-TW', zhTW],
];

// Only the subtrees the row view addresses by key; `errors` is addressed by verdict code at runtime.
const ROW_SUBTREES = ['status', 'technical', 'components', 'hints'] as const;

function resolve(messages: Messages, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
      messages.settings.systemHealth.doctor,
    );
}

function leafKeys(node: unknown, prefix: string): string[] {
  if (node && typeof node === 'object') {
    return Object.entries(node).flatMap(([key, child]) => leafKeys(child, `${prefix}.${key}`));
  }
  return [prefix];
}

describe.each(LOCALES)('doctor row locale keys in %s', (_locale, messages) => {
  it('has a non-empty text for every key the row view can reference', () => {
    const missing = DOCTOR_LOCALE_KEYS.filter((key) => {
      const value = resolve(messages, key);
      return typeof value !== 'string' || value.trim() === '';
    });

    expect(missing).toEqual([]);
  });

  it('carries no row text the row view never references', () => {
    const doctor = messages.settings.systemHealth.doctor as Record<string, unknown>;
    const present = ROW_SUBTREES.flatMap((subtree) => leafKeys(doctor[subtree], subtree));

    expect(present.filter((key) => !DOCTOR_LOCALE_KEYS.includes(key))).toEqual([]);
  });
});
