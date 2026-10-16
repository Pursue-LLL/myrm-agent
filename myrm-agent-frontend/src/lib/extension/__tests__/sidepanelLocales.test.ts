/**
 * Side Panel copy: every message key the panel asks `chrome.i18n` for exists in both extension locales.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const EXTENSION_DIR = resolve(__dirname, '../../../../../myrm-agent-extension');
const read = (relativePath: string) => readFileSync(resolve(EXTENSION_DIR, relativePath), 'utf8');

type Catalog = Record<string, { message: string; placeholders?: Record<string, unknown> }>;
const catalogs = {
  en: JSON.parse(read('_locales/en/messages.json')) as Catalog,
  zh_CN: JSON.parse(read('_locales/zh_CN/messages.json')) as Catalog,
};

/** Keys named in `msg("...")`, `translate("...")` calls and `data-i18n="..."` attributes of the side panel sources. */
function referencedKeys(): string[] {
  const keys = new Set<string>();
  for (const file of ['src/sidepanel/sidepanel.js', 'src/sidepanel/approval.js']) {
    for (const match of read(file).matchAll(/(?:msg|translate)\(\s*"(\w+)"/g)) {
      keys.add(match[1]);
    }
  }
  for (const match of read('src/sidepanel/sidepanel.html').matchAll(/data-i18n="(\w+)"/g)) {
    keys.add(match[1]);
  }
  return [...keys].sort();
}

describe('side panel locale keys', () => {
  it('finds the keys the panel uses', () => {
    expect(referencedKeys()).toEqual(
      expect.arrayContaining([
        'approvalApprove',
        'approvalHandledElsewhere',
        'approvalSendFailed',
        'approvalTitleBatch',
      ]),
    );
  });

  it.each(Object.keys(catalogs) as (keyof typeof catalogs)[])(
    'has a message for every referenced key in %s',
    (locale) => {
      const missing = referencedKeys().filter((key) => !catalogs[locale][key]?.message);

      expect(missing).toEqual([]);
    },
  );

  it('keeps the same keys and placeholders in both locales', () => {
    expect(Object.keys(catalogs.zh_CN).sort()).toEqual(Object.keys(catalogs.en).sort());
    for (const [key, entry] of Object.entries(catalogs.en)) {
      expect(Object.keys(catalogs.zh_CN[key].placeholders ?? {}), key).toEqual(Object.keys(entry.placeholders ?? {}));
    }
  });
});
